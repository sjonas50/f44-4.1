from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql://localhost:5432/sovereign_agent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # AWS S3 WORM Storage
    AWS_S3_WORM_BUCKET: str = "sovereign-agent-worm"
    AWS_REGION: str = "us-east-1"
    WORM_RETENTION_YEARS: int = 7

    # HashiCorp Vault
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = ""

    # Base L2 Anchoring
    BASE_L2_RPC_URL: str = ""
    BASE_L2_RPC_FALLBACK_URL: str = ""
    ANCHOR_CONTRACT_ADDRESS: str = ""
    ANCHOR_INTERVAL_SECONDS: int = 300
    BASE_CHAIN_ID: int = 84532  # 84532 = Base Sepolia, 8453 = Base mainnet
    DEPLOYER_PRIVATE_KEY: str = ""  # Hex private key for signing anchor transactions
    ALCHEMY_API_KEY: str = ""
    QUICKNODE_API_KEY: str = ""

    # JWT / Auth
    JWT_SIGNING_KEY: str = ""

    # ASOR Integration
    ASOR_VC_ENDPOINT: str = "http://localhost:8000/vc/issue"
    ASOR_BASE_URL: str = "http://localhost:8000"

    # Application
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    model_config = {"env_file": ".env", "extra": "ignore"}
