from pydantic import BaseSettings
from pydantic import SecretStr

class DBsettings(BaseSettings):
    """Settings model for database connections."""

    pghost: str = "ldap-db"
    app_database: str = "ldap-integration"
    app_dbuser: str = "postgres"
    app_dbpassword: SecretStr
