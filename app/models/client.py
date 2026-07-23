# Re-export client from user module file split — Client lives in user.py for FK simplicity
from app.models.user import Client

__all__ = ["Client"]
