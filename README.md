# Codelog: Process-based Programming Assessment & Behavior Analysis System
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18440045.svg)](https://doi.org/10.5281/zenodo.18440045)

## Introduction

**Codelog** is a comprehensive system designed for **process-based programming assessment** and **coding behavior analysis**. Developed for computing education and learning analytics research, this system enables educators to monitor students' coding processes in real-time, evaluate problem-solving behaviors, and manage longitudinal coding data for educational insights.

## Getting Started

### Prerequisites

- [Docker](https://www.docker.com/)

### Installation & Deployment

1. **Prepare the Package**: Extract the provided zip file into your desired directory.

2. **Configure Environment Variables**:

Copy the `.env.example` file to `.env` and configure your credentials (e.g., MongoDB passwords).

```bash
cp .env.example .env
```

3. **Run the System**:

Use Docker Compose to build and start all containers in detached mode.

```bash
docker-compose up -d --build
```

## System Structure & Port Mapping

The system is built on a microservices architecture. All services are isolated within Docker containers and communicate via an internal bridge network.

| **Service** | **External Port** | **Internal Port** | **Description** |
| ------------------- | ----------------- | ----------------- | --------------------------------------------------|
| **Flask App** | `8080` | `8080` | Main web server for assessment and monitoring. |
| **Lambda Lite** | `9100` | `8080` | Sandboxed Python code execution engine (FastAPI). |
| **MongoDB Active** | `27017` | `27017` | Storage for real-time session and student data. |
| **MongoDB Archive** | `27018` | `27017` | Isolated storage for historical/longitudinal data. |

## 4. License & Intellectual Property Notice

### 4.1. License

This project is licensed under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)**.

**Copyright (c) 2026 Sol Chung [solution@knue.ac.kr](mailto:solution@knue.ac.kr)** **Supervised by Prof. Seung-Hyun Kim (Korea National University of Education)**

### 4.2. Patent & Usage Policy (⚠️)

**Notice**: The core technologies and methodologies implemented in this software are protected by a pending patent application in the Republic of Korea.

- **Application Number**: 10-2025-0092125

- **Title**: 프로그래밍 학습 과정 기록, 재생 및 피드백 제공 시스템 (System for Recording, Replaying, and Providing Feedback in Programming Learning Process)

- **Inventors**: Sol Chung, Seung-Hyun Kim

**Terms of Use**:

- **Non-Commercial**: Redistribution or exploitation of the code and the patented methods for commercial purposes is **strictly prohibited** without prior written consent from the patent holders.

- **Attribution**: Any reuse or modification must provide appropriate credit to the author (**Sol Chung**) and indicate the supervision of **Prof. Seung-Hyun Kim**.

- **ShareAlike**: Derivative works must be distributed under the same CC BY-NC-SA 4.0 license.

## 5. Citation (Required)

To ensure academic integrity and support the sustainability of this research, please cite this system in any research papers or derivative software:
> **Chung, S. (2026). Codelog: Process-based Programming Assessment & Behavior Analysis System (v1.0.0). Zenodo. https://doi.org/10.5281/zenodo.18440045**