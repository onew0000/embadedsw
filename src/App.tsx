import React, { useState, useEffect } from 'react';
import './App.css';
// import io from 'socket.io-client';

function App() {
  const [selectedPart, setSelectedPart] = useState('Part 1');
  const [selectedLeg, setSelectedLeg] = useState('L');
  const [similarRate, setSimilarRate] = useState(76);
  const [strength, setStrength] = useState(3);
  const [autoSet, setAutoSet] = useState(true);
  const [autoTuningProgress, setAutoTuningProgress] = useState(45);
  const [arduinoConnected, setArduinoConnected] = useState(false);
  const [calibrated, setCalibrated] = useState(false);
  const [emgData, setEmgData] = useState({ reference: 0, current: 0 });
  const [socket, setSocket] = useState(null);

  const parts = ['Part 1', 'Part 2', 'Part 3'];
  const legs = ['L', 'R'];

  useEffect(() => {
    // Socket.IO 연결 (주석 처리 - 패키지 설치 후 활성화)
    // const newSocket = io('http://localhost:5000');
    // setSocket(newSocket);

    // newSocket.on('connect', () => {
    //   console.log('서버 연결됨');
    // });

    // newSocket.on('emg_data', (data: any) => {
    //   setEmgData(data);
    //   // 유사도 계산 (간단한 예시)
    //   if (data.reference > 0 && data.current > 0) {
    //     const similarity = Math.min(100, Math.max(0, (1 - Math.abs(data.reference - data.current) / data.reference) * 100));
    //     setSimilarRate(Math.round(similarity));
    //   }
    // });

    // newSocket.on('status', (status: any) => {
    //   setArduinoConnected(status.arduino_connected);
    //   setCalibrated(status.calibrated);
    // });

    // return () => {
    //   newSocket.close();
    // };
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setAutoTuningProgress(prev => (prev + 1) % 101);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  const connectArduino = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const result = await response.json();
      if (result.success) {
        setArduinoConnected(true);
        alert('아두이노 연결 성공');
      } else {
        alert('아두이노 연결 실패: ' + result.message);
      }
    } catch (error: any) {
      alert('연결 오류: ' + error.message);
    }
  };

  const calibrateSystem = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/calibrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const result = await response.json();
      if (result.success) {
        setCalibrated(true);
        alert('캘리브레이션 완료');
      } else {
        alert('캘리브레이션 실패: ' + result.message);
      }
    } catch (error: any) {
      alert('캘리브레이션 오류: ' + error.message);
    }
  };

  const controlMotor = async (speed: number, direction: number) => {
    try {
      const response = await fetch('http://localhost:5000/api/motor_control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speed, direction })
      });
      const result = await response.json();
      if (!result.success) {
        alert('모터 제어 실패: ' + result.message);
      }
    } catch (error: any) {
      alert('모터 제어 오류: ' + error.message);
    }
  };

  return (
    <div className="app">
      {/* Header Card */}
      <div className="header-card">
        <div className="header-content">
          <div className="header-text">
            <h1 className="app-title">Fine Leg</h1>
            <p className="app-subtitle">We fine-tuning your leg.</p>
          </div>
          <div className="leg-selector">
            {legs.map(leg => (
              <button
                key={leg}
                className={`leg-button ${selectedLeg === leg ? 'active' : ''}`}
                onClick={() => setSelectedLeg(leg)}
              >
                {leg}
              </button>
            ))}
          </div>
        </div>
        <div className="connection-status">
          <div className={`status-indicator ${arduinoConnected ? 'connected' : 'disconnected'}`}>
            {arduinoConnected ? '아두이노 연결됨' : '아두이노 연결 안됨'}
          </div>
          <div className={`status-indicator ${calibrated ? 'calibrated' : 'not-calibrated'}`}>
            {calibrated ? '캘리브레이션 완료' : '캘리브레이션 필요'}
          </div>
        </div>
        <div className="control-buttons">
          <button 
            className="control-btn connect-btn" 
            onClick={connectArduino}
            disabled={arduinoConnected}
          >
            아두이노 연결
          </button>
          <button 
            className="control-btn calibrate-btn" 
            onClick={calibrateSystem}
            disabled={!arduinoConnected || calibrated}
          >
            캘리브레이션
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="nav-tabs">
        {parts.map(part => (
          <button
            key={part}
            className={`nav-tab ${selectedPart === part ? 'active' : ''}`}
            onClick={() => setSelectedPart(part)}
          >
            {part}
          </button>
        ))}
      </div>

      {/* Current Selection */}
      <div className="current-selection">
        Jaemin's {selectedLeg === 'L' ? 'Left' : 'Right'} Leg
      </div>

      {/* Similar-Rate Gauge */}
      <div className="gauge-container">
        <div className="gauge">
          <div className="gauge-outer">
            <div 
              className="gauge-fill" 
              style={{ 
                background: `conic-gradient(#007AFF 0deg ${similarRate * 3.6}deg, rgba(255,255,255,0.2) ${similarRate * 3.6}deg 360deg)`
              }}
            ></div>
          </div>
          <div className="gauge-center">
            <div className="gauge-label">Similar-Rate</div>
            <div className="gauge-value">{similarRate}%</div>
          </div>
        </div>
      </div>

      {/* Auto-Tuning Section */}
      <div className="auto-tuning-section">
        <div className="auto-tuning-header">
          <div className="loading-spinner"></div>
          <span>Auto-Tuning</span>
        </div>
        <div className="progress-bar">
          <div 
            className="progress-fill" 
            style={{ width: `${autoTuningProgress}%` }}
          ></div>
        </div>
      </div>

      {/* Strength Control Card */}
      <div className="strength-card">
        <div className="strength-content">
          <div className="strength-info">
            <div className="strength-label">
              {selectedPart} - Strength {strength}Lv
            </div>
            <div className="strength-slider">
              <div className="slider-track">
                {[1, 2, 3, 4, 5].map(level => (
                  <div 
                    key={level} 
                    className={`slider-dot ${level <= strength ? 'active' : ''}`}
                  ></div>
                ))}
              </div>
              <input
                type="range"
                min="1"
                max="5"
                value={strength}
                onChange={(e) => setStrength(parseInt(e.target.value))}
                className="slider-input"
              />
            </div>
          </div>
          <div className="auto-set-toggle">
            <span className="toggle-label">Auto-Set</span>
            <button
              className={`toggle-switch ${autoSet ? 'active' : ''}`}
              onClick={() => setAutoSet(!autoSet)}
            >
              <div className="toggle-thumb"></div>
            </button>
          </div>
        </div>
        <div className="motor-controls">
          <button 
            className="motor-btn pull-btn"
            onClick={() => controlMotor(50, 0)}
            disabled={!calibrated}
          >
            당기기
          </button>
          <button 
            className="motor-btn release-btn"
            onClick={() => controlMotor(0, 1)}
            disabled={!calibrated}
          >
            놓기
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;