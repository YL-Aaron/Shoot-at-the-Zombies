"""入口配置和所有入口共用的战斗配置，不依赖界面或图像识别组件。"""

from dataclasses import asdict, dataclass, field, fields


def normalize_mode(mode, huanqiu_entry='channel'):
    if mode == 3:
        return 0, 'invite'
    return (1 if mode == 1 else 0), (
        'invite' if huanqiu_entry == 'invite' else 'channel'
    )


@dataclass
class BaseConfig:
    game_title: str = '向僵尸开炮'
    mode: int = 0
    huanqiu_entry: str = 'channel'
    group_wait_timeout: int = 30

    def __post_init__(self):
        self.mode, self.huanqiu_entry = normalize_mode(self.mode, self.huanqiu_entry)


@dataclass
class BattleConfig:
    battle_count: int = 0
    battle_time: int = 0
    priority_skills: list[str] = field(default_factory=list)
    exit_on_mode_mismatch: bool = True
    prioritize_biochemical_bullet: bool = True


def load_settings(data):
    """读取分组配置，同时兼容旧版扁平字段及 mode=3。"""
    def section(name, config_type):
        values = {f.name: data[f.name] for f in fields(config_type) if f.name in data}
        values.update({
            f.name: data.get(name, {})[f.name]
            for f in fields(config_type) if f.name in data.get(name, {})
        })
        return config_type(**values)

    base, battle = section('base', BaseConfig), section('battle', BattleConfig)
    old = {**data, **data.get('battle', {})}
    if 'exit_on_mode_mismatch' not in old:
        # 旧版任意退出保护开启时，迁移为统一的模式保护。
        battle.exit_on_mode_mismatch = (
            old.get('exit_normal_stage_on_huanqiu', True)
            or old.get('exit_deep_abyss', False)
        )
    return base, battle


def dump_settings(base, battle):
    return {'base': asdict(base), 'battle': asdict(battle)}
