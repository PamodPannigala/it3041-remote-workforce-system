from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.modules.auth.constants import GENERAL_API_RATE_LIMIT


limiter = Limiter(
    key_func=get_remote_address,
    application_limits=[GENERAL_API_RATE_LIMIT],
)