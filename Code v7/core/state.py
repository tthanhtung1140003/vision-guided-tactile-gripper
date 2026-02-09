class SystemState:
    def __init__(self):
        self.pos = [0.0, 0.0, 0.0]  
        self.speed = [0.0, 0.0, 0.0]
        self.limits = "---"
        self.target_pos = [0.0, 0.0, 0.0]  
        self.fw_state = None  
        self.fw_err = None   
        self.connected = False
        self.points = []   
        self.paths = {}
        self.active_point_index = -1
