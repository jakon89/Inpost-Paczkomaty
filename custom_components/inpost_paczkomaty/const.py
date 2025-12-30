"""Constants for the InPost Paczkomaty integration."""

DOMAIN = "inpost_paczkomaty"

# Config entry keys
ENTRY_PHONE_NUMBER_CONFIG = "phone_number"

# OAuth2 token storage keys
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_TOKEN_EXPIRES_IN = "token_expires_in"
CONF_TOKEN_TYPE = "token_type"

# =============================================================================
# OAuth2 Configuration
# =============================================================================

# Base URLs for InPost services
OAUTH_BASE_URL = "https://account.inpost-group.com"
API_BASE_URL = "https://api-inmobile-pl.easypack24.net"

# OAuth2 client configuration
OAUTH_CLIENT_ID = "inpost-mobile"
OAUTH_REDIRECT_URI = "https://account.inpost-group.com/callback"
API_USER_AGENT = "InPost-Mobile/4.4.2 (1)-release (iOS 26.2; iPhone15,3; pl)"
