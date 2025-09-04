// 아두이노 근전도 센서 및 모터 제어 코드
// EMG 센서 2개 (정상 다리, 비정상 다리)와 스테핑 모터 제어

#include <Stepper.h>

// 스테핑 모터 설정
const int stepsPerRevolution = 200;
Stepper myStepper(stepsPerRevolution, 8, 9, 10, 11);

// EMG 센서 핀 설정
const int EMG_HEALTHY_PIN = A0;    // 정상 다리 EMG 센서
const int EMG_PATIENT_PIN = A1;    // 비정상 다리 EMG 센서

// 모터 제어 변수
int motorSpeed = 0;
int motorDirection = 0;
bool motorActive = false;

// EMG 데이터 변수
float emgHealthy = 0;
float emgPatient = 0;

// 시리얼 통신 버퍼
String inputString = "";
bool stringComplete = false;

void setup() {
  // 시리얼 통신 초기화
  Serial.begin(115200);
  
  // 스테핑 모터 초기화
  myStepper.setSpeed(30);
  
  // EMG 센서 핀 설정
  pinMode(EMG_HEALTHY_PIN, INPUT);
  pinMode(EMG_PATIENT_PIN, INPUT);
  
  // 시리얼 버퍼 예약
  inputString.reserve(200);
  
  Serial.println("EMG Rehabilitation System Ready");
  delay(1000);
}

void loop() {
  // EMG 데이터 읽기
  readEMGData();
  
  // 시리얼 명령 처리
  if (stringComplete) {
    processSerialCommand();
    inputString = "";
    stringComplete = false;
  }
  
  // 모터 제어
  controlMotor();
  
  delay(10); // 100Hz 샘플링
}

void readEMGData() {
  // EMG 센서 값 읽기 (0-1023 -> 0-5V -> 마이크로볼트 변환)
  int healthyRaw = analogRead(EMG_HEALTHY_PIN);
  int patientRaw = analogRead(EMG_PATIENT_PIN);
  
  // 아날로그 값을 마이크로볼트로 변환 (예시: 5V = 5000μV)
  emgHealthy = (float)healthyRaw * (5000.0 / 1023.0);
  emgPatient = (float)patientRaw * (5000.0 / 1023.0);
  
  // 시리얼로 데이터 전송
  Serial.print("EMG:");
  Serial.print(emgHealthy, 1);
  Serial.print(",");
  Serial.println(emgPatient, 1);
}

void processSerialCommand() {
  if (inputString.startsWith("MOTOR:")) {
    // 모터 명령 파싱: "MOTOR:speed,direction"
    String command = inputString.substring(6); // "MOTOR:" 제거
    
    int commaIndex = command.indexOf(',');
    if (commaIndex > 0) {
      motorSpeed = command.substring(0, commaIndex).toInt();
      motorDirection = command.substring(commaIndex + 1).toInt();
      
      // 모터 활성화/비활성화 결정
      motorActive = (motorSpeed > 0);
      
      Serial.print("Motor command received: Speed=");
      Serial.print(motorSpeed);
      Serial.print(", Direction=");
      Serial.println(motorDirection);
    }
  }
}

void controlMotor() {
  if (motorActive) {
    // 모터 속도 설정
    myStepper.setSpeed(motorSpeed);
    
    // 방향에 따른 모터 회전
    if (motorDirection == 0) {
      // 정방향 (당기기)
      myStepper.step(1);
    } else {
      // 역방향 (놓기)
      myStepper.step(-1);
    }
  }
}

void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }
}

// 추가 유틸리티 함수들
void emergencyStop() {
  motorActive = false;
  motorSpeed = 0;
  Serial.println("EMERGENCY STOP");
}

void calibrateEMG() {
  // EMG 센서 캘리브레이션 (기준값 설정)
  float sumHealthy = 0;
  float sumPatient = 0;
  int samples = 100;
  
  for (int i = 0; i < samples; i++) {
    sumHealthy += analogRead(EMG_HEALTHY_PIN);
    sumPatient += analogRead(EMG_PATIENT_PIN);
    delay(10);
  }
  
  float avgHealthy = sumHealthy / samples;
  float avgPatient = sumPatient / samples;
  
  Serial.print("Calibration - Healthy: ");
  Serial.print(avgHealthy);
  Serial.print(", Patient: ");
  Serial.println(avgPatient);
}
