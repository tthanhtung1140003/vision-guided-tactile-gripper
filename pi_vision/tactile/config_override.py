#config_override.py
from tactile.config_base import TactileConfig

def get_config(cam_id: int):
    cfg = TactileConfig().clone()

    if cam_id == 1:
        cfg.cx0, cfg.cy0 = 178, 96
        cfg.spacing = 86
        cfg.radius = 15

        p = cfg.make_blob_params()
        p.minArea = 500
        p.maxArea = 899
        cfg.blob_params = p
    else:
        cfg.blob_params = cfg.make_blob_params()

    return cfg