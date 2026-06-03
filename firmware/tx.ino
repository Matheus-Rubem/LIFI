/*
  LiFi TX firmware — Arduino Uno/Nano (ATmega328P).
  Spec: docs/superpowers/specs/2026-04-21-lifi-vlc-design.md §4.

  Responsibility:
    - Read bytes from USB serial at 115200 baud into a 128-byte circular buffer.
    - At 2.5 Hz (400 ms/bit), emit each byte as 10 UART-over-light bits on pin D8:
        start(0) + 8 data LSB-first + stop(1)
    - When buffer empty, hold LED HIGH (IDLE).

  NOTE: bit rate lowered from 5 Hz to 2.5 Hz so a typical webcam (15-25 fps)
  gets ~6-10 samples/bit instead of ~3. The receiver MUST decode with the
  matching rate: `python -m src.rx --mode white --bit-rate 2.5`.

  Design: Timer1 in CTC mode drives the bit emitter ISR. loop() just fills the
  buffer. No SoftwareSerial — all bit timing is controlled by Timer1.
*/

#include <Arduino.h>

constexpr uint8_t LED_PIN = 8;
constexpr uint8_t INDICATOR_PIN = 13;          // optional on-board LED
constexpr size_t BUF_SIZE = 128;               // exactly one max frame
constexpr uint16_t OCR1A_VAL = 6249;           // 400 ms at 16 MHz / prescaler 1024

volatile uint8_t  buf[BUF_SIZE];
volatile size_t   head = 0;
volatile size_t   tail = 0;
volatile uint8_t  current_byte = 0;
volatile uint8_t  bit_index = 10;              // 10 = idle (not transmitting)

// ---- helpers ----

inline bool buf_empty()  { return head == tail; }
inline bool buf_full()   { return ((head + 1) % BUF_SIZE) == tail; }

inline void buf_push(uint8_t v) {
  buf[head] = v;
  head = (head + 1) % BUF_SIZE;
}

inline bool buf_pop(uint8_t *out) {
  if (buf_empty()) return false;
  *out = buf[tail];
  tail = (tail + 1) % BUF_SIZE;
  return true;
}

// ---- setup ----

void setup() {
  pinMode(LED_PIN, OUTPUT);
  pinMode(INDICATOR_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);                 // IDLE high
  digitalWrite(INDICATOR_PIN, LOW);

  Serial.begin(115200);

  // Timer1 CTC: 16 MHz / 1024 / 6250 = 2.5 Hz -> OCR1A = 6249
  noInterrupts();
  TCCR1A = 0;
  TCCR1B = (1 << WGM12) | (1 << CS12) | (1 << CS10);  // CTC, prescaler 1024
  OCR1A  = OCR1A_VAL;
  TIMSK1 = (1 << OCIE1A);
  TCNT1  = 0;
  interrupts();
}

// ---- bit emitter ----

ISR(TIMER1_COMPA_vect) {
  // Emit one bit per tick.
  if (bit_index == 10) {
    // Idle or looking for next byte.
    if (!buf_pop((uint8_t*)&current_byte)) {
      digitalWrite(LED_PIN, HIGH);             // IDLE high
      digitalWrite(INDICATOR_PIN, LOW);
      return;
    }
    digitalWrite(INDICATOR_PIN, HIGH);
    bit_index = 0;
  }

  uint8_t level;
  if (bit_index == 0) {
    level = 0;                                 // start bit
  } else if (bit_index == 9) {
    level = 1;                                 // stop bit
  } else {
    // data bits: LSB-first, bit i corresponds to current_byte bit (bit_index-1)
    level = (current_byte >> (bit_index - 1)) & 0x01;
  }

  digitalWrite(LED_PIN, level ? HIGH : LOW);
  bit_index++;
}

// ---- main loop ----

void loop() {
  while (Serial.available() > 0) {
    if (buf_full()) {
      // Spin until ISR drains. ISR runs every 200ms; a full buffer drains in 256s.
      // Python side is throttled by serial write block here.
      break;
    }
    int b = Serial.read();
    if (b < 0) break;
    noInterrupts();
    buf_push((uint8_t)b);
    interrupts();
  }
}
