#include <AS5600.h>
#include <Wire.h>
#include <EEPROM.h>

// --- CẤU HÌNH CHÂN ---
#define STEP_PIN PA1  
#define DIR_PIN  PA0  
#define EN_PIN   PA2

#define DIR_CLOSE LOW
#define DIR_OPEN  HIGH

// --- CẤU HÌNH TỐC ĐỘ & GIỚI HẠN ---
#define DEFAULT_SPEED 2000.0  // Tốc độ mặc định (bước/giây)
#define MAX_SPEED_HARD 6000.0 // Giới hạn cứng của phần cứng

#define ANGLE_MIN -3.0   
#define ANGLE_MAX 725.0  

// --- PID ---
float Kp = 30.0;
float Ki = 0.05;
float Kd = 200.0;

AS5600 encoder;

// --- BIẾN HỆ THỐNG ---
long revolutions = 0;
float lastRawAngle = 0.0;
float rawTotalAngle = 0.0; 
float zeroOffset = 0.0;    

float currentAngle = 0.0;  
float targetAngle = 0.0;

// --- FLASH (EEPROM) ---
#define EEPROM_MAGIC_ADDR 0     
#define EEPROM_DATA_ADDR  10    
#define MAGIC_NUMBER      0x45  

// --- VARIABLES ---
float pidOutput = 0.0;
float error = 0, lastError = 0, integral = 0;

enum State { PID_HOLD, MOVING_VELOCITY };
State currentState = PID_HOLD;
float moveSpeed = 0.0;

const byte numChars = 64;
char receivedChars[numChars];
boolean newData = false;

unsigned long lastStepTime = 0;
unsigned long stepInterval = 0;
unsigned long lastPrint = 0;

// ==========================================
//  FLASH HELPERS
// ==========================================
void saveToFlash(float angle) {
  EEPROM.put(EEPROM_DATA_ADDR, angle);
}

float loadFromFlash() {
  float val;
  EEPROM.get(EEPROM_DATA_ADDR, val);
  return val;
}

void initFlashIfNeeded() {
  byte flag = EEPROM.read(EEPROM_MAGIC_ADDR); 
  if (flag != MAGIC_NUMBER) {
    Serial.println("<EEPROM:FIRST_RUN_INIT_ZERO>");
    saveToFlash(0.0); 
    EEPROM.write(EEPROM_MAGIC_ADDR, MAGIC_NUMBER); 
  } else {
    Serial.println("<EEPROM:DATA_FOUND>");
  }
}

// ==========================================
//  SETUP
// ==========================================
void setup() {
  Serial.begin(115200);

  Wire.setSDA(PB9);
  Wire.setSCL(PB8);
  Wire.begin();
  Wire.setClock(400000);

  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(EN_PIN, OUTPUT);
  digitalWrite(EN_PIN, LOW); 

  delay(100);

  if (!encoder.begin()) {
    pinMode(PC13, OUTPUT);
    while (1) { digitalWrite(PC13, !digitalRead(PC13)); delay(100); }
  }

  EEPROM.begin(); 
  initFlashIfNeeded(); 

  for(int i = 0; i < 10; i++) {
     encoder.readAngle();
     delay(5);
  }

  float startRaw = encoder.readAngle() * 0.08789;
  lastRawAngle = startRaw;
  revolutions = 0;
  rawTotalAngle = startRaw; 

  float savedAngle = loadFromFlash(); 
  
  zeroOffset = rawTotalAngle - savedAngle;
  currentAngle = rawTotalAngle - zeroOffset;

  if (currentAngle > ANGLE_MAX) {
    float diff = currentAngle - ANGLE_MAX;
    zeroOffset += diff; 
    currentAngle = ANGLE_MAX; 
  }
  else if (currentAngle < ANGLE_MIN) {
    float diff = currentAngle - ANGLE_MIN;
    zeroOffset += diff;
    currentAngle = ANGLE_MIN;
  }

  targetAngle = currentAngle; 

  currentState = PID_HOLD;
  integral = 0;
  lastError = 0;
  pidOutput = 0;

  Serial.print("<READY:POS_RESTORED:");
  Serial.print(currentAngle);
  Serial.println(">");
}

// ==========================================
//  LOOP
// ==========================================
void loop() {
  recvWithStartEndMarkers();
  if (newData) {
    parseData();
    newData = false;
  }

  readSensor();

  // --- SAFETY ---
  if (currentState == MOVING_VELOCITY) {
    if (moveSpeed < 0 && currentAngle <= ANGLE_MIN) {
      currentState = PID_HOLD; targetAngle = ANGLE_MIN; moveSpeed = 0;
    }
    else if (moveSpeed > 0 && currentAngle >= ANGLE_MAX) {
      currentState = PID_HOLD; targetAngle = ANGLE_MAX; moveSpeed = 0;
    }
  }
  
  // --- PID ---
  if (currentState == PID_HOLD) {
    if (targetAngle < ANGLE_MIN) targetAngle = ANGLE_MIN;
    if (targetAngle > ANGLE_MAX) targetAngle = ANGLE_MAX;

    error = targetAngle - currentAngle;
    
    if (abs(error) < 0.3) {
      pidOutput = 0; integral = 0;
    } else {
      integral += error;
      if (integral > 2000) integral = 2000;
      if (integral < -2000) integral = -2000;
      
      float derivative = error - lastError;
      pidOutput = (Kp * error) + (Ki * integral) + (Kd * derivative);
      lastError = error;
    }
  } else {
    pidOutput = moveSpeed;
    targetAngle = currentAngle; 
    integral = 0; lastError = 0;
  }

  runStepper(pidOutput);

  if (millis() - lastPrint > 50) {
    Serial.print("<ANG:"); Serial.print(currentAngle);
    Serial.print(",TAR:"); Serial.print(targetAngle);
    Serial.println(">");
    lastPrint = millis();
  }
}

// ==========================================
//  HELPERS & PARSER (CẬP NHẬT)
// ==========================================

void parseData() {
  char * strtokIndx;
  strtokIndx = strtok(receivedChars, ":");
  char cmd = strtokIndx[0];
  
  float val = 0.0;
  strtokIndx = strtok(NULL, ":"); // Lấy phần sau dấu :
  if (strtokIndx != NULL) val = atof(strtokIndx);

  switch (cmd) {
    case 'G': // Grip (Có thể chỉnh tốc độ)
      currentState = MOVING_VELOCITY; 
      {
        // Nếu val = 0 (không nhập) -> Hệ số = 1.0
        // Nếu val > 0 -> Hệ số = val
        float factor = (val > 0.001) ? val : 1.0;
        moveSpeed = DEFAULT_SPEED * factor;
        
        // Giới hạn tốc độ tối đa
        if (moveSpeed > MAX_SPEED_HARD) moveSpeed = MAX_SPEED_HARD;
      }
      break;
      
    case 'R': // Release (Có thể chỉnh tốc độ)
      currentState = MOVING_VELOCITY; 
      {
        float factor = (val > 0.001) ? val : 1.0;
        moveSpeed = -1.0 * DEFAULT_SPEED * factor; // Số âm để quay ngược
        
        if (moveSpeed < -MAX_SPEED_HARD) moveSpeed = -MAX_SPEED_HARD;
      }
      break;
    
    case 'F': currentState = PID_HOLD; targetAngle = currentAngle; break;

    case 'T': 
      if (val < ANGLE_MIN) val = ANGLE_MIN;
      if (val > ANGLE_MAX) val = ANGLE_MAX;
      currentState = PID_HOLD; targetAngle = val; 
      break;

    case 'S': currentState = PID_HOLD; targetAngle += 5.0; break;
    case 'L': currentState = PID_HOLD; targetAngle -= 5.0; break;

    case 'Z': 
      zeroOffset = rawTotalAngle; 
      currentAngle = 0; targetAngle = 0; integral = 0;
      currentState = PID_HOLD;
      saveToFlash(0.0); 
      Serial.println("<ZERO:DONE>");
      break;

    case 'K': 
      saveToFlash(currentAngle);
      Serial.println("<FLASH:SAVED>");
      break;
  }
}

void readSensor() {
  float raw = encoder.readAngle() * 0.08789;
  float delta = raw - lastRawAngle;

  if (delta < -300) revolutions++;
  else if (delta > 300) revolutions--;

  lastRawAngle = raw;
  rawTotalAngle = (revolutions * 360.0) + raw;
  currentAngle = rawTotalAngle - zeroOffset;
}

void runStepper(float speed) {
  if (speed == 0) return;
  if (speed > 0) digitalWrite(DIR_PIN, DIR_CLOSE);
  else { digitalWrite(DIR_PIN, DIR_OPEN); speed = -speed; }
  
  if (speed > MAX_SPEED_HARD) speed = MAX_SPEED_HARD;
  if (speed < 10) return;

  stepInterval = 1000000.0 / speed;
  unsigned long now = micros();
  if (now - lastStepTime >= stepInterval) {
    digitalWrite(STEP_PIN, HIGH);
    delayMicroseconds(2);
    digitalWrite(STEP_PIN, LOW);
    lastStepTime = now;
  }
}

void recvWithStartEndMarkers() {
  static boolean recvInProgress = false;
  static byte ndx = 0;
  char startMarker = '<';
  char endMarker = '>';
  char rc;
  while (Serial.available() > 0 && newData == false) {
    rc = Serial.read();
    if (recvInProgress) {
      if (rc != endMarker) {
        receivedChars[ndx++] = rc;
        if (ndx >= numChars) ndx = numChars - 1;
      } else {
        receivedChars[ndx] = '\0';
        recvInProgress = false;
        ndx = 0;
        newData = true;
      }
    } else if (rc == startMarker) recvInProgress = true;
  }
}