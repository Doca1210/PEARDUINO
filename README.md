# 🌳 PearTree — Real-Time Urban Tree Health Monitoring System

PearTree is a real-time embedded system that monitors the health of urban trees using low-cost sensors and edge computing. It transforms each tree into a continuously observed biological sensor, combining structural vibration analysis with environmental data to compute a live tree stress index.

The system is designed for cities like Barcelona, where heatwaves, drought, and hidden structural decay are increasingly threatening urban vegetation.

---

## 🚨 Problem

Urban trees suffer from:
- Heat stress and drought conditions
- Internal decay and hollowing (invisible externally)
- Structural weakening due to environmental stress
- Lack of continuous monitoring systems

Current solutions are:
- Manual inspections (rare, subjective, expensive)
- Satellite imaging (low resolution, indirect)
- Reactive rather than continuous

---

## 💡 Solution

PearTree turns every tree into a real-time monitoring node:

- Measures **structural response** using vibration sensing (accelerometer)
- Measures **environmental stress** using temperature & humidity
- Computes a **live Stress Index (0–100)**
- Translates health state into an intuitive “Tree Mood”
- Provides a public interface and chatbot for interaction

---

## 🧠 Key Idea

Instead of treating trees as passive objects, PearTree treats them as:
> continuously measurable living infrastructure nodes inside a city-wide sensor network

---

## ⚙️ Hardware

- Arduino UNO Q
- Modulino Movement (3-axis accelerometer)
- Modulino Thermo (temperature + humidity)
- Qwiic I2C connections

---

## 🧮 System Overview

### 1. Data Acquisition
- Vibration sampled at ~62.5 Hz
- Temperature & humidity sampled periodically

### 2. Signal Processing
- Acceleration magnitude extraction
- Sliding window buffering (128 samples)
- Noise filtering and stabilization

### 3. Feature Extraction
- RMS energy
- FFT dominant frequency
- Spectral centroid
- Temporal decay rate

### 4. Anomaly Detection
- Baseline learned per tree
- Mahalanobis distance used for deviation scoring

### 5. Environmental Stress Model
- Temperature rate of change (°C/s)
- Humidity deviation from optimal range (40–70%)

### 6. Stress Index
Combined score:
- Structural stress (vibration)
- Environmental stress (heat + humidity)

Output: **0–100 Tree Stress Index**

---

## 🌿 Interactive Layer

Each tree has a public-facing interface that:
- Displays real-time health status
- Converts stress index into an intuitive “mood”
- Allows users to interact with a chatbot powered by a generative AI API

The chatbot is grounded in live sensor data and reflects the current physiological state of the tree.

---

## 🤖 AI Components

- Unsupervised anomaly detection (no labeled dataset required)
- Edge-based feature extraction
- Generative AI chatbot conditioned on tree health state

---

## 🌐 Data Flow
