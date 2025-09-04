# EMG 기반 다리 재활 시스템

아두이노와 웹을 연동한 근전도 센서 기반 다리 재활 시스템입니다.

## 시스템 구성

### 하드웨어
- 아두이노 우노/나노
- EMG 센서 2개 (정상 다리, 비정상 다리)
- 스테핑 모터 (다리 당기기/놓기)
- USB 케이블 (아두이노-PC 연결)

### 소프트웨어
- Python Flask 서버 (백엔드)
- React 웹 인터페이스 (프론트엔드)
- 아두이노 펌웨어

## 설치 및 실행

### 1. Python 환경 설정
```bash
# 가상환경 생성 (선택사항)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 필요한 패키지 설치
pip install -r requirements.txt
```

### 2. Node.js 환경 설정
```bash
# React 앱 의존성 설치
npm install
```

### 3. 아두이노 설정
1. `arduino_code.ino` 파일을 아두이노 IDE에서 열기
2. 필요한 라이브러리 설치 (Stepper 라이브러리는 기본 포함)
3. 아두이노에 업로드

### 4. 하드웨어 연결
- EMG 센서 1: A0 핀 (정상 다리)
- EMG 센서 2: A1 핀 (비정상 다리)
- 스테핑 모터: 8, 9, 10, 11 핀

### 5. 실행
```bash
# 터미널 1: Python 서버 실행
python server.py

# 터미널 2: React 앱 실행
npm start
```

## 사용법

### 1. 시스템 초기화
1. 웹 브라우저에서 `http://localhost:3000` 접속
2. "아두이노 연결" 버튼 클릭
3. 연결 상태가 "아두이노 연결됨"으로 변경되면 성공

### 2. 캘리브레이션
1. 정상 다리에 EMG 센서 부착
2. "캘리브레이션" 버튼 클릭
3. 3-5초간 정상 다리 근육 수축
4. "캘리브레이션 완료" 메시지 확인

### 3. 재활 운동
1. 비정상 다리에 EMG 센서 부착
2. 실시간 유사도 확인 (Similar-Rate 게이지)
3. 자동 모드: Auto-Set 토글 활성화
4. 수동 모드: "당기기"/"놓기" 버튼 사용

## API 엔드포인트

### GET /api/status
시스템 상태 확인
```json
{
  "arduino_connected": true,
  "calibrated": true,
  "data_count": 150
}
```

### POST /api/connect
아두이노 연결
```json
{
  "success": true,
  "message": "아두이노 연결 성공"
}
```

### POST /api/calibrate
캘리브레이션 실행
```json
{
  "success": true,
  "message": "캘리브레이션 완료",
  "reference_value": 1234.5
}
```

### POST /api/motor_control
모터 제어
```json
{
  "speed": 50,
  "direction": 0
}
```

## 알고리즘 설명

### 1. EMG 신호 처리
- 대역통과 필터링 (20-450Hz)
- 60Hz 노치 필터 (전원 노이즈 제거)
- RMS 엔벨로프 추출
- TKEO 기반 발화 탐지

### 2. 유사도 측정
- 정상 다리 기준값과 비정상 다리 실시간 값 비교
- 정규화된 활성도 계산
- SNR 기반 신호 품질 평가

### 3. 모터 제어
- PI 제어기 기반 보조 출력
- 히스테리시스 적용
- 안전 제한 (램프, 포화)

## 문제 해결

### 아두이노 연결 실패
- 시리얼 포트 확인 (Windows: COM3, macOS/Linux: /dev/ttyUSB0)
- 아두이노 드라이버 설치 확인
- USB 케이블 연결 상태 확인

### EMG 데이터 수신 안됨
- 센서 연결 상태 확인
- 아두이노 시리얼 모니터에서 데이터 확인
- 센서 전원 공급 확인

### 모터 작동 안됨
- 모터 드라이버 연결 확인
- 전원 공급 확인
- 아두이노 코드 업로드 확인

## 개발자 정보

- Python Flask 서버: `server.py`
- React 웹 인터페이스: `src/App.tsx`
- EMG 알고리즘: `src/app.py`
- 아두이노 펌웨어: `arduino_code.ino`

## 라이선스

MIT License