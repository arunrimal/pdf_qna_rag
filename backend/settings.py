from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

# 1. Define the nested configuration structure
class AppConfig(BaseModel):
    app_name: str = Field(alias="App_Name")
    db_path: str = Field(alias="Db_path")
    collection_name: str = Field(alias="Collection_Name")
    port: int = Field(alias="PORT")        # Will auto-convert "8080" to 8080
    host: str = Field(alias="HOST")

# 2. Define the Main Settings
class Settings(BaseSettings):
    api_key: SecretStr = Field(alias="API_KEY")
    app_config: AppConfig = Field(alias="APP_CONFIG")

    # 3. V2 Configuration
    model_config = SettingsConfigDict(
        # Point to your JSON file. 
        # Using __file__ ensures it looks relative to this python file.
        # env_file=Path(__file__).parent / "config.json", 
        env_file=".env", 
        env_file_encoding='utf-8',
        case_sensitive=True,  # Important: Your JSON keys are uppercase/mixed
        extra='ignore'        # Ignore extra fields in JSON not defined here
    )

# Initialize once
try:
    settings = Settings()
except Exception as e:
    print(f"Failed to load settings: {e}")
    raise

# --- Usage Example ---
if __name__ == "__main__":
    # Accessing values
    print(f"App: {settings.app_config.app_name}")
    print(f"Port: {settings.app_config.port}") # This is an int now
    print(f"Host: {settings.app_config.host}")
    
    # API Key is a SecretStr, get it with .get_secret_value()
    print(f"Key: {settings.api_key.get_secret_value()}")