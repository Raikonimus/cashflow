"""Tests for Partner management (Bolt 004)."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import UserRole
from tests.partners.conftest import (
    assign_user_to_mandant,
    create_mandant,
    create_user,
    get_auth_token,
)


async def create_partner(
    client: AsyncClient,
    token: str,
    mandant_id,
    name: str = "Amazon EU",
    iban: str | None = None,
) -> dict:
    body: dict = {"name": name}
    if iban:
        body["iban"] = iban
    resp = await client.post(
        f"/api/v1/mandants/{mandant_id}/partners",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
class TestPartnerCRUD:

    async def test_create_partner(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        assert partner["name"] == "Amazon EU"
        assert partner["ibans"] == []

    async def test_create_partner_with_iban(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id, iban="DE89370400440532013000")
        assert len(partner["ibans"]) == 1
        assert partner["ibans"][0]["iban"] == "DE89370400440532013000"

    async def test_duplicate_partner_name_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        await create_partner(client, token, mandant.id, "Duplicate Corp")
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners",
            json={"name": "Duplicate Corp"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    async def test_viewer_cannot_create_partner(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        viewer = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, viewer, mandant)
        token = await get_auth_token(client, viewer, mandant)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners",
            json={"name": "Sneaky Partner"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    async def test_viewer_can_list_partners(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        viewer = await create_user(db_session, "viewer@test.com", UserRole.viewer)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, viewer, mandant)
        token = await get_auth_token(client, viewer, mandant)
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert "items" in resp.json()

    async def test_list_partners_pagination(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        for i in range(5):
            await create_partner(client, token, mandant.id, f"Partner {i}")
        resp = await client.get(
            f"/api/v1/mandants/{mandant.id}/partners?page=1&size=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 3
        assert body["pages"] == 2


@pytest.mark.asyncio
class TestPartnerIban:

    async def test_add_iban_to_partner(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/ibans",
            json={"iban": "DE89 3704 0044 0532 0130 00"},  # with spaces
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["iban"] == "DE89370400440532013000"  # normalized

    async def test_global_iban_uniqueness(self, client: AsyncClient, db_session: AsyncSession):
        """ADR-008: IBAN must be globally unique across all partners."""
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        p1 = await create_partner(client, token, mandant.id, "Partner 1")
        p2 = await create_partner(client, token, mandant.id, "Partner 2")
        iban = "LU96013000000726000067"
        await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{p1['id']}/ibans",
            json={"iban": iban}, headers={"Authorization": f"Bearer {token}"}
        )
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{p2['id']}/ibans",
            json={"iban": iban}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 409


@pytest.mark.asyncio
class TestPartnerNameVariants:

    async def test_add_name_variant(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/names",
            json={"name": "AMZ MARKETPLACE"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "AMZ MARKETPLACE"

    async def test_duplicate_name_within_partner_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/names",
            json={"name": "Duplicate"}, headers={"Authorization": f"Bearer {token}"}
        )
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/names",
            json={"name": "Duplicate"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 409


@pytest.mark.asyncio
class TestPartnerPatterns:

    async def test_add_string_pattern(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/patterns",
            json={"pattern": "amazon", "pattern_type": "string", "match_field": "description"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["pattern"] == "amazon"

    async def test_add_valid_regex_pattern(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/patterns",
            json={"pattern": r"amaz(on|on\.de)", "pattern_type": "regex", "match_field": "description"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    async def test_invalid_regex_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/patterns",
            json={"pattern": "[invalid((", "pattern_type": "regex", "match_field": "description"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
        assert "Invalid regex" in resp.json()["detail"]

    async def test_delete_pattern(self, client: AsyncClient, db_session: AsyncSession):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        create_resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/patterns",
            json={"pattern": "test", "pattern_type": "string", "match_field": "description"},
            headers={"Authorization": f"Bearer {token}"},
        )
        pattern_id = create_resp.json()["id"]
        del_resp = await client.delete(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/patterns/{pattern_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_resp.status_code == 204

    async def test_duplicate_pattern_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user = await create_user(db_session, "acc@test.com", UserRole.accountant)
        mandant = await create_mandant(db_session)
        await assign_user_to_mandant(db_session, user, mandant)
        token = await get_auth_token(client, user, mandant)
        partner = await create_partner(client, token, mandant.id)
        payload = {"pattern": "amazon", "pattern_type": "string", "match_field": "description"}
        await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/patterns",
            json=payload, headers={"Authorization": f"Bearer {token}"}
        )
        resp = await client.post(
            f"/api/v1/mandants/{mandant.id}/partners/{partner['id']}/patterns",
            json=payload, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 409
