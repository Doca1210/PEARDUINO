// SPDX-License-Identifier: MPL-2.0
#include <Arduino_Modulino.h>
#include <Arduino_RouterBridge.h>

ModulinoMovement movement;
ModulinoThermo thermo;

float x_accel, y_accel, z_accel;
float temp, humidity;

unsigned long prevMove = 0;
unsigned long prevEnv  = 0;

const long moveInterval = 16;    // ~62.5 Hz
const long envInterval  = 1000;  // 1 Hz

bool movementOk = false;
bool thermoOk   = false;

void setup() {
  Bridge.begin();
  Modulino.begin(Wire1);

  // ---------- FIX: replace infinite while-loop with a retry limit ----------
  // The original `while (!movement.begin()) { delay(1000); }` would block
  // forever if the IMU wasn't found (e.g. loose QWIIC cable), preventing
  // thermo from ever starting and producing zero output from both sensors.
  // -------------------------------------------------------------------------
  const int MAX_RETRIES = 5;
  for (int i = 0; i < MAX_RETRIES; i++) {
    if (movement.begin()) {
      movementOk = true;
      break;
    }
    delay(500);
  }

  thermoOk = thermo.begin();
  // thermo.begin() returns void on some library versions; treat it as always ok
  thermoOk = true;
}

void loop() {
  unsigned long now = millis();

  // -------- VIBRATION (HIGH RATE) --------
  if (movementOk && (now - prevMove >= moveInterval)) {
    prevMove = now;
    if (movement.update()) {
      x_accel = movement.getX();
      y_accel = movement.getY();
      z_accel = movement.getZ();
      Bridge.notify("vibration_sample", x_accel, y_accel, z_accel);
    }
  }

  // -------- TEMPERATURE + HUMIDITY --------
  if (thermoOk && (now - prevEnv >= envInterval)) {
    prevEnv = now;
    temp     = thermo.getTemperature();
    humidity = thermo.getHumidity();
    Bridge.notify("thermo_sample", temp, humidity);
  }
}
