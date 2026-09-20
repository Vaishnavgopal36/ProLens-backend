from app.core.azure_ad import AzureADClient
from app.core.google_client import GoogleClient
from app.models.enums import SSOProvider
from app.models.sso import SSOConnection


def get_sso_client(connection: SSOConnection):
    if connection.provider == SSOProvider.azure_ad:
        return AzureADClient(
            connection.tenant_id, connection.client_id, connection.client_secret
        )
    if connection.provider == SSOProvider.google:
        return GoogleClient(connection.client_id, connection.client_secret)

    raise ValueError(f"Unsupported SSO provider: {connection.provider}")