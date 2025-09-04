from dataclasses import dataclass
import numpy as np
from scipy.signal import butter, filtfilt, iirnotch
import time

# ====== Arduino 시리얼 어댑터 ======
try:
    import serial
except ImportError:
    serial = None

class ArduinoLink:
    def __init__(self, port="COM5", baud=115200, timeout=0.05):
        if serial is None:
            raise RuntimeError("pyserial이 설치되어 있지 않습니다. pip install pyserial 로 설치하세요.")
        self.ser = serial.Serial(port, baudrate=baud, timeout=timeout)
        time.sleep(2.0)  # 아두이노 자동리셋 대기

    def send_u(self, u: float, retract_mm: float):
        line = f"CMD u={u:.3f},mm={retract_mm:.1f}\n".encode()
        self.ser.write(line)

    def notify(self, msg: str):
        print(f"[PHONE] {msg}")

_link = None

def init_link(port="COM5", baud=115200):
    global _link
    _link = ArduinoLink(port=port, baud=baud)

# =========================
# 구성요소: 설정 및 유틸
# =========================

@dataclass
class EMGConfig:
    fs: float = 1000.0
    bp_low: float = 20.0
    bp_high: float = 450.0
    notch: float = 60.0
    notch_q: float = 30.0
    rms_win_ms: float = 200.0
    tkeo_win_ms: float = 50.0
    ref_percentile: float = 95.0
    target_activation: float = 0.5
    onset_thresh_z: float = 2.0
    noise_cv_thresh: float = 0.35
    snr_db_thresh: float = 8.0
    low_act_thresh: float = 0.3
    low_act_hold_s: float = 2.0
    assist_kp: float = 0.8
    assist_ki: float = 0.1
    assist_ramp_max: float = 0.2
    assist_max: float = 1.0
    assist_min: float = 0.0
    hysteresis: float = 0.05
    safety_drop_db: float = -20.0
    safety_spike_sigma: float = 8.0

def bandpass_notch(x, cfg: EMGConfig):
    nyq = cfg.fs / 2.0
    b, a = butter(4, [cfg.bp_low/nyq, cfg.bp_high/nyq], btype='bandpass')
    y = filtfilt(b, a, x)
    b0, a0 = iirnotch(cfg.notch/nyq, cfg.notch_q)
    y = filtfilt(b0, a0, y)
    return y

def rms_envelope(x, cfg: EMGConfig):
    win = int(max(1, cfg.rms_win_ms/1000.0 * cfg.fs))
    cumsum = np.cumsum(np.insert(x**2, 0, 0.0))
    r = np.sqrt((cumsum[win:] - cumsum[:-win]) / win)
    pad = win//2
    return np.pad(r, (pad, len(x)-len(r)-pad), mode='edge')

def tkeo(x):
    y = np.zeros_like(x)
    y[1:-1] = x[1:-1]**2 - x[:-2]*x[2:]
    return y

def smooth(x, win_samps):
    if win_samps <= 1:
        return x
    k = np.ones(win_samps)/win_samps
    return np.convolve(x, k, mode='same')

def snr_db(sig, noise):
    ps = np.mean(sig**2) + 1e-12
    pn = np.mean(noise**2) + 1e-12
    return 10*np.log10(ps/pn)

# =========================
# 캘리브레이션: 건측 기준값
# =========================

@dataclass
class CalibrationResult:
    A_ref: float
    noise_level: float

def calibrate_reference(emg_healthy_raw: np.ndarray, cfg: EMGConfig) -> CalibrationResult:
    x = bandpass_notch(emg_healthy_raw, cfg)
    env = rms_envelope(np.abs(x), cfg)
    A_ref = np.percentile(env, cfg.ref_percentile)
    p10 = np.percentile(env, 10.0)
    noise = np.mean(env[env <= p10]) + 1e-9
    return CalibrationResult(A_ref=max(A_ref, 1e-6), noise_level=noise)

# =========================
# 발화 탐지 및 특징 추출
# =========================

@dataclass
class EMGFeatures:
    onset_idx: int
    mean_act: float
    act_cv: float
    snr_db: float

def detect_onset_and_features(emg_raw: np.ndarray, A_ref: float, cfg: EMGConfig) -> EMGFeatures:
    x = bandpass_notch(emg_raw, cfg)
    env = rms_envelope(np.abs(x), cfg)
    a = env / A_ref
    e = tkeo(x)
    e = np.maximum(e, 0.0)
    e = smooth(e, int(max(1, cfg.tkeo_win_ms/1000.0*cfg.fs)))
    ez = (e - np.median(e)) / (np.std(e) + 1e-9)
    onset_idx = int(np.argmax(ez > cfg.onset_thresh_z)) if np.any(ez > cfg.onset_thresh_z) else 0
    win = int(1.5*cfg.fs)
    seg = a[onset_idx:onset_idx+win] if onset_idx+win <= len(a) else a[onset_idx:]
    mean_act = float(np.mean(seg)) if len(seg) > 10 else float(np.mean(a))
    act_cv = float(np.std(seg)/(np.mean(seg)+1e-9)) if len(seg) > 10 else float(np.std(a)/(np.mean(a)+1e-9))
    pre = a[max(0, onset_idx-int(0.5*cfg.fs)):onset_idx]
    post = a[onset_idx:onset_idx+int(0.5*cfg.fs)]
    _snr = snr_db(post if len(post)>10 else a, pre if len(pre)>10 else a*0+np.mean(a)*0.1)
    return EMGFeatures(onset_idx=onset_idx, mean_act=mean_act, act_cv=act_cv, snr_db=float(_snr))

# =========================
# 분류: 자세 의심 vs 저활성 의심
# =========================

@dataclass
class Assessment:
    label: str
    confidence: float
    deficit: float

def assess(features: EMGFeatures, cfg: EMGConfig) -> Assessment:
    d = max(0.0, cfg.target_activation - features.mean_act)
    posture_flag = (features.act_cv >= cfg.noise_cv_thresh) or (features.snr_db < cfg.snr_db_thresh)
    lowact_flag = (features.mean_act < cfg.low_act_thresh) and not posture_flag
    if posture_flag and d > 0:
        return Assessment("posture_suspect", confidence=min(0.9, 0.5 + 0.5*d), deficit=d)
    if lowact_flag and d > 0:
        return Assessment("hypoactivation_suspect", confidence=min(0.9, 0.4 + 0.8*d), deficit=d)
    return Assessment("ok", confidence=0.7, deficit=0.0)

# =========================
# 보조 제어: PI + 램프/포화/히스테리시스
# =========================

class AssistController:
    def __init__(self, cfg: EMGConfig):
        self.cfg = cfg
        self.int_err = 0.0
        self.last_u = 0.0
        self.assist_on = False

    def step(self, deficit: float, dt: float) -> float:
        self.int_err += deficit * dt
        u = self.cfg.assist_kp * deficit + self.cfg.assist_ki * self.int_err
        if not self.assist_on and u > self.cfg.hysteresis:
            self.assist_on = True
        if self.assist_on and u < (self.cfg.hysteresis/2):
            self.assist_on = False
        u = u if self.assist_on else 0.0
        du_max = self.cfg.assist_ramp_max * dt
        u = np.clip(u, self.last_u - du_max, self.last_u + du_max)
        u = float(np.clip(u, self.cfg.assist_min, self.cfg.assist_max))
        self.last_u = u
        return u

# =========================
# 안전 감시
# =========================

def safety_guard(emg_raw: np.ndarray, cfg: EMGConfig) -> bool:
    x = bandpass_notch(emg_raw, cfg)
    zx = (x - np.mean(x)) / (np.std(x) + 1e-9)
    spike = np.any(np.abs(zx) > cfg.safety_spike_sigma)
    half = len(x)//2
    if half < 10:
        return False
    s1 = snr_db(x[:half], x[:half] - np.mean(x[:half]))
    s2 = snr_db(x[half:], x[half:] - np.mean(x[half:]))
    drop = (s2 - s1) < cfg.safety_drop_db
    return bool(spike or drop)

# =========================
# 스마트폰/모터 I/F → Arduino 전송으로 교체
# =========================

def send_to_phone(msg: str):
    if _link:
        _link.notify(msg)
    else:
        print(f"[PHONE] {msg}")

def motor_command_from_assist(u: float):
    target_retraction_mm = 20.0 * u
    if _link:
        _link.send_u(u, target_retraction_mm)
    else:
        target_speed_rpm = 30.0 * (0.5 + u)
        print(f"[MOTOR] retract_mm={target_retraction_mm:.1f}, speed_rpm={target_speed_rpm:.1f}")

# =========================
# 메인 루프 예시 (스트리밍 가정)
# =========================

class RehabAlgorithm:
    def __init__(self, cfg: EMGConfig):
        self.cfg = cfg
        self.ctrl = AssistController(cfg)
        self.state_lowact_timer = 0.0

    def calibrate(self, emg_healthy_raw: np.ndarray) -> CalibrationResult:
        return calibrate_reference(emg_healthy_raw, self.cfg)

    def run_once(self, emg_patient_raw: np.ndarray, calib: CalibrationResult, dt: float):
        if safety_guard(emg_patient_raw, self.cfg):
            send_to_phone("안전 경고: 신호 이상 감지. 전극/자세 확인 후 재시도하세요.")
            motor_command_from_assist(0.0)
            self.ctrl.int_err = 0.0
            return

        feats = detect_onset_and_features(emg_patient_raw, calib.A_ref, self.cfg)
        result = assess(feats, self.cfg)

        if result.label == "posture_suspect":
            send_to_phone("자세/전극 의심: 전극 접촉·피부청결·자세 정렬 확인. 가이드 영상을 재생합니다.")
            motor_command_from_assist(0.0)
            self.state_lowact_timer = 0.0
            return

        if result.label == "hypoactivation_suspect":
            self.state_lowact_timer += dt
            if self.state_lowact_timer >= self.cfg.low_act_hold_s:
                u = self.ctrl.step(result.deficit, dt)
                send_to_phone(f"저활성 의심: 보조 구동 {u:.2f} 비율 적용.")
                motor_command_from_assist(u)
            else:
                send_to_phone("저활성 경향 관찰 중: 2초 이상 지속 시 보조를 시작합니다.")
                motor_command_from_assist(0.0)
            return

        self.state_lowact_timer = 0.0
        u = self.ctrl.step(0.0, dt)
        motor_command_from_assist(u)
        send_to_phone("활성이 충분합니다. 보조 없이 진행합니다.")

# =========================
# 사용 예시 (데모 신호) 테스트
# =========================

if __name__ == "__main__":
    cfg = EMGConfig(fs=1000.0, notch=60.0)
    init_link("COM5", baud=9600)  # 실제 연결 시 포트명으로 활성화

    rng = np.random.default_rng(0)

    t = np.arange(0, 12.0, 1/cfg.fs)
    healthy = 0.02*rng.standard_normal(len(t))
    for s in [2, 5, 8, 10]:
        idx = (t > s) & (t < s+1.0)
        healthy[idx] += 0.3*np.sin(2*np.pi*80*t[idx])

    algo = RehabAlgorithm(cfg)
    calib = algo.calibrate(healthy)
    print(f"A_ref={calib.A_ref:.4f}, noise={calib.noise_level:.5f}")

    t2 = np.arange(0, 3.0, 1/cfg.fs)
    patient_posture = 0.03*rng.standard_normal(len(t2)) + 0.05*np.sin(2*np.pi*2*t2)
    patient_posture += 0.12*np.sin(2*np.pi*70*t2)*(t2>1.0)
    algo.run_once(patient_posture, calib, dt=3.0)

    patient_low = 0.02*rng.standard_normal(len(t2))
    patient_low += 0.08*np.sin(2*np.pi*90*t2)*(t2>0.5)
    algo.run_once(patient_low, calib, dt=3.0)

    patient_ok = 0.02*rng.standard_normal(len(t2))
    patient_ok += 0.25*np.sin(2*np.pi*100*t2)*(t2>0.5)
    algo.run_once(patient_ok, calib, dt=3.0)
