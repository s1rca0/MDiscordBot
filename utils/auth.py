from config import OWNERS

def is_owner(user_id: int) -> bool:
    return user_id in OWNERS