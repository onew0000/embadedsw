from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import serial
import threading
import time
import json
import numpy as np
from app import RehabAlgorithm, EMGConfig, CalibrationResult
import queue
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# 전역 변수
arduino_serial = None
emg_algorithm = None
calibration_data = None
is_calibrated = False
current_emg_data = []
reference_emg_data = []
motor_control_queue = queue.Queue()
data_lock = threading.Lock()

# 아두이노 시리얼 통신 설정
SERIAL_PORT = 'COM3'  # Windows의 경우, macOS/Linux는 '/dev/ttyUSB0' 또는 '/dev/ttyACM0'
BAUD_RATE = 115200

class ArduinoInterface:
    def __init__(self, port, baud_rate):
        self.port = port
        self.baud_rate = baud_rate
        self.serial_conn = None
        self.is_connected = False
        
    def connect(self):
        try:
            self.serial_conn = serial.Serial(self.port, self.baud_rate, timeout=1)
            time.sleep(2)  # 아두이노 초기화 대기
            self.is_connected = True
            logger.info(f"아두이노 연결 성공: {self.port}")
            return True
        except Exception as e:
            logger.error(f"아두이노 연결 실패: {e}")
            return False
    
    def disconnect(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            self.is_connected = False
            logger.info("아두이노 연결 해제")
    
    def read_emg_data(self):
        """아두이노로부터 근전도 데이터 읽기"""
        if not self.is_connected or not self.serial_conn:
            return None
            
        try:
            line = self.serial_conn.readline().decode('utf-8').strip()
            if line:
                # 예상 형식: "EMG:1234.5" 또는 "EMG:1234.5,5678.9" (정상, 비정상)
                if line.startswith("EMG:"):
                    data_str = line[4:]  # "EMG:" 제거
                    values = [float(x) for x in data_str.split(',')]
                    return values
        except Exception as e:
            logger.error(f"데이터 읽기 오류: {e}")
            return None
    
    def send_motor_command(self, motor_speed, motor_direction):
        """모터 제어 명령 전송"""
        if not self.is_connected or not self.serial_conn:
            return False
            
        try:
            command = f"MOTOR:{motor_speed},{motor_direction}\n"
            self.serial_conn.write(command.encode())
            logger.info(f"모터 명령 전송: {command.strip()}")
            return True
        except Exception as e:
            logger.error(f"모터 명령 전송 실패: {e}")
            return False

# 아두이노 인터페이스 초기화
arduino = ArduinoInterface(SERIAL_PORT, BAUD_RATE)

def arduino_data_thread():
    """아두이노 데이터 수신 스레드"""
    global current_emg_data, reference_emg_data, is_calibrated
    
    while True:
        if arduino.is_connected:
            data = arduino.read_emg_data()
            if data:
                with data_lock:
                    if len(data) == 2:  # 정상, 비정상 다리 데이터
                        reference_emg_data.append(data[0])  # 정상 다리
                        current_emg_data.append(data[1])    # 비정상 다리
                        
                        # 데이터 길이 제한 (메모리 관리)
                        if len(reference_emg_data) > 1000:
                            reference_emg_data = reference_emg_data[-1000:]
                        if len(current_emg_data) > 1000:
                            current_emg_data = current_emg_data[-1000:]
                        
                        # 웹소켓으로 실시간 데이터 전송
                        socketio.emit('emg_data', {
                            'reference': data[0],
                            'current': data[1],
                            'timestamp': time.time()
                        })
                        
                        # 캘리브레이션된 경우 알고리즘 실행
                        if is_calibrated and emg_algorithm and len(current_emg_data) >= 100:
                            process_emg_data()
                    elif len(data) == 1:  # 단일 데이터 (캘리브레이션용)
                        reference_emg_data.append(data[0])
                        if len(reference_emg_data) > 1000:
                            reference_emg_data = reference_emg_data[-1000:]
                        
                        socketio.emit('emg_data', {
                            'reference': data[0],
                            'current': 0,
                            'timestamp': time.time()
                        })
        
        time.sleep(0.01)  # 100Hz 샘플링

def process_emg_data():
    """근전도 데이터 처리 및 모터 제어"""
    global current_emg_data, calibration_data
    
    if not calibration_data or len(current_emg_data) < 100:
        return
    
    try:
        # 최근 3초 데이터 사용 (1000Hz 기준)
        recent_data = np.array(current_emg_data[-3000:])
        
        # 알고리즘 실행
        emg_algorithm.run_once(recent_data, calibration_data, dt=3.0)
        
        # 모터 제어 큐에서 명령 처리
        while not motor_control_queue.empty():
            command = motor_control_queue.get()
            arduino.send_motor_command(command['speed'], command['direction'])
            
    except Exception as e:
        logger.error(f"데이터 처리 오류: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """시스템 상태 반환"""
    return jsonify({
        'arduino_connected': arduino.is_connected,
        'calibrated': is_calibrated,
        'data_count': len(current_emg_data)
    })

@app.route('/api/calibrate', methods=['POST'])
def calibrate():
    """정상 다리 근전도 캘리브레이션"""
    global calibration_data, is_calibrated, emg_algorithm
    
    try:
        if not arduino.is_connected:
            return jsonify({'success': False, 'message': '아두이노가 연결되지 않았습니다.'})
        
        if len(reference_emg_data) < 100:
            return jsonify({'success': False, 'message': '캘리브레이션 데이터가 부족합니다.'})
        
        # EMG 알고리즘 초기화
        config = EMGConfig(fs=1000.0, notch=60.0)
        emg_algorithm = RehabAlgorithm(config)
        
        # 캘리브레이션 실행
        reference_array = np.array(reference_emg_data[-1000:])  # 최근 1초 데이터
        calibration_data = emg_algorithm.calibrate(reference_array)
        is_calibrated = True
        
        logger.info(f"캘리브레이션 완료: A_ref={calibration_data.A_ref:.4f}")
        
        return jsonify({
            'success': True, 
            'message': '캘리브레이션 완료',
            'reference_value': calibration_data.A_ref
        })
        
    except Exception as e:
        logger.error(f"캘리브레이션 오류: {e}")
        return jsonify({'success': False, 'message': f'캘리브레이션 실패: {str(e)}'})

@app.route('/api/connect', methods=['POST'])
def connect_arduino():
    """아두이노 연결"""
    try:
        if arduino.connect():
            return jsonify({'success': True, 'message': '아두이노 연결 성공'})
        else:
            return jsonify({'success': False, 'message': '아두이노 연결 실패'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'연결 오류: {str(e)}'})

@app.route('/api/disconnect', methods=['POST'])
def disconnect_arduino():
    """아두이노 연결 해제"""
    try:
        arduino.disconnect()
        return jsonify({'success': True, 'message': '아두이노 연결 해제'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'해제 오류: {str(e)}'})

@app.route('/api/motor_control', methods=['POST'])
def motor_control():
    """모터 수동 제어"""
    try:
        data = request.json
        speed = data.get('speed', 0)
        direction = data.get('direction', 0)  # 0: 정방향, 1: 역방향
        
        if arduino.is_connected:
            motor_control_queue.put({'speed': speed, 'direction': direction})
            return jsonify({'success': True, 'message': '모터 명령 전송'})
        else:
            return jsonify({'success': False, 'message': '아두이노가 연결되지 않았습니다.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'모터 제어 오류: {str(e)}'})

@socketio.on('connect')
def handle_connect():
    logger.info('클라이언트 연결됨')
    emit('status', {
        'arduino_connected': arduino.is_connected,
        'calibrated': is_calibrated
    })

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('클라이언트 연결 해제됨')

if __name__ == '__main__':
    # 아두이노 데이터 수신 스레드 시작
    arduino_thread = threading.Thread(target=arduino_data_thread, daemon=True)
    arduino_thread.start()
    
    # Flask 서버 시작
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
