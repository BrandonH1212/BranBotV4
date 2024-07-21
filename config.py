from dataclasses import dataclass
from typing import Optional
import os
import json


@dataclass
class Server:
    name: str
    serverID: int
    disabled_cogs: list[str]

    def json(self):
        return {"name": self.name, "serverID": self.serverID, "disabled_cogs": self.disabled_cogs}

@dataclass
class Preset:
    name: str
    api_keys: dict[str, str]
    servers: list[str]
    
    def json(self):
        return {"name": self.name, "api_keys": self.api_keys, "servers": self.servers}
    
@dataclass
class Config:
    presets: list[Preset]
    servers: list[Server]
    active_preset: str = 'default'
    _instance: Optional['Config'] = None
    
    def get_api_key(self, service: str) -> str:
        default = self.presets[0].api_keys.get(service, None)
        
        for preset in self.presets:
            if preset.name == self.active_preset:
                return preset.api_keys.get(service, default)
        
        return default
    
    def get_servers(self, cog_name:str = 'default') -> list[int]:
        servers = []
        for preset in self.presets:
            if preset.name == self.active_preset:
                for server in preset.servers:
                    servers.append(server)
                        
        if len(servers) == 0:
            return None
                    
        return [server.serverID for server in self.servers if server.name in servers]
        
    def json(self):
        return {"presets": [preset.json() for preset in self.presets], "servers": [server.json() for server in self.servers]}
    
    @staticmethod
    def create():
        return Config(
            presets=[Preset(
                name='default',
                api_keys={'discord': 'your_key_here', 'osu_id':00000 ,'osu_secret': 'your_key_here', 'openai': 'your_key_here'},
                servers=['default']
                )
            ],
            servers=[Server(
                name='default',
                serverID=0,
                disabled_cogs=[]
                )
            ])
    
    @staticmethod
    def load(active_preset='default') -> 'Config':
        with open("config.json", "r") as f:
            data = json.load(f)
        presets = [Preset(**preset) for preset in data["presets"]]
        servers = [Server(**server) for server in data["servers"]]
        return Config(active_preset=active_preset, presets=presets, servers=servers)
    
    def save(self):
        with open("config.json", "w") as f:
            json.dump(self.json(), f, indent=4)
            
    @classmethod
    def get_instance(cls) -> 'Config':
        if cls._instance is None:
            cls._instance = cls.load()
        return cls._instance

if __name__ == "__main__": 
    if not os.path.exists("config.json"):
        Config.create().save()
        
    config = Config.get_instance()
    print(config.presets)
    print(config.servers)
    print('loaded config')

else:
    # global config
    config = Config.get_instance()

    
