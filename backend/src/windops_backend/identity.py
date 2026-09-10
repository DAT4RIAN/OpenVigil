from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hmac import compare_digest
from math import isfinite

import jwt
from jwt import InvalidTokenError

APPLICATION_ROLES = frozenset(
    {
        "operations_manager",
        "operations_approver",
        "maintenance_reviewer",
        "field_technician",
    }
)


class IdentityError(Exception):
    """Base class for safe delegated-identity failures."""


class InvalidIdentityError(IdentityError):
    """The delegation is invalid, expired, or bound to another request."""


class IdentityRoleError(IdentityError):
    """The authenticated Sites user has no OpenVigil application role."""


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: str
    email: str | None
    roles: tuple[str, ...]
    delegation_id: str
    expires_at: datetime


class DelegatedIdentityAuthenticator:
    """Validate a short-lived Sites gateway assertion bound to one backend request."""

    def __init__(
        self,
        *,
        secrets: tuple[str, ...],
        issuer: str,
        audience: str,
        role_mappings: dict[str, list[str]],
        clock_skew_seconds: int,
    ) -> None:
        self.secrets = secrets
        self.issuer = issuer
        self.audience = audience
        self.role_mappings = role_mappings
        self.clock_skew_seconds = clock_skew_seconds

    def authenticate(
        self,
        token: str,
        *,
        request_method: str,
        request_target: str,
        body_sha256: str,
    ) -> VerifiedIdentity:
        last_error: InvalidTokenError | None = None
        raw_claims: dict[str, object] | None = None
        for secret in self.secrets:
            try:
                raw_claims = jwt.decode(
                    token,
                    secret,
                    algorithms=["HS256"],
                    audience=self.audience,
                    issuer=self.issuer,
                    leeway=self.clock_skew_seconds,
                    options={"require": ["exp", "iat", "jti", "sub"]},
                )
                break
            except InvalidTokenError as exc:
                last_error = exc
        if raw_claims is None:
            raise InvalidIdentityError("delegated identity validation failed") from last_error

        claims = raw_claims
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise InvalidIdentityError("delegated identity subject is missing")
        delegation_id = claims.get("jti")
        if (
            not isinstance(delegation_id, str)
            or not delegation_id.strip()
            or len(delegation_id.strip()) > 256
        ):
            raise InvalidIdentityError("delegated identity jti is invalid")
        raw_expiry = claims.get("exp")
        if (
            isinstance(raw_expiry, bool)
            or not isinstance(raw_expiry, (int, float))
            or not isfinite(float(raw_expiry))
        ):
            raise InvalidIdentityError("delegated identity expiry is invalid")
        try:
            expires_at = datetime.fromtimestamp(float(raw_expiry), UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise InvalidIdentityError("delegated identity expiry is invalid") from exc
        expected = {
            "method": request_method.upper(),
            "target": request_target,
            "body_sha256": body_sha256,
        }
        for name, expected_value in expected.items():
            actual = claims.get(name)
            if not isinstance(actual, str) or not compare_digest(actual, expected_value):
                raise InvalidIdentityError("delegated identity is bound to another request")

        roles = tuple(
            sorted(
                {role for role in self.role_mappings.get(subject, []) if role in APPLICATION_ROLES}
            )
        )
        if not roles:
            raise IdentityRoleError("the authenticated Sites user has no OpenVigil role")
        raw_email = claims.get("email")
        email = raw_email.strip() if isinstance(raw_email, str) and raw_email.strip() else None
        return VerifiedIdentity(
            subject=subject.strip(),
            email=email,
            roles=roles,
            delegation_id=delegation_id.strip(),
            expires_at=expires_at,
        )
