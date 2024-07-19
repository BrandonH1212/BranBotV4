from ossapi import OssapiAsync, Scope, Beatmap, User, Score, GameMode
from config import config


def get_osu_api() -> OssapiAsync:
    api = OssapiAsync(client_id=config.get_api_key('osu_id'), client_secret=config.get_api_key('osu_secret'))
    return api
    
async def get_osu_user(name_or_id: str) -> User:
    api = get_osu_api()
    try:
        user = await api.user(name_or_id)
        return user
    except Exception as e:
        return None
    