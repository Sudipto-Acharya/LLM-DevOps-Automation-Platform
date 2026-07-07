<p align="center">
  <img src="assets/banner.png" alt="DevOps AI Agent Banner" width="100%">
</p>

<h1 align="center">🤖 AI-Powered DevOps Automation Agent</h1>

<p align="center">
  An intelligent DevOps assistant that deploys and manages a full 3-tier AWS infrastructure<br>
  through natural language commands — zero manual intervention required.
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![AWS](https://img.shields.io/badge/AWS-boto3-orange.svg)
![Jenkins](https://img.shields.io/badge/Jenkins-Automation-red.svg)
![Docker](https://img.shields.io/badge/Docker-Containers-blue.svg)
![Groq](https://img.shields.io/badge/Groq-Llama%203.3%2070B-green.svg)
![License](https://img.shields.io/badge/License-MIT-success.svg)

</p>

---

# 📌 About

Managing cloud infrastructure typically means juggling multiple AWS consoles, SSH sessions, Jenkins dashboards, deployment pipelines, and monitoring tools — all manually, all error-prone.

This project demonstrates how a **Large Language Model (LLM)** can be integrated with **AWS**, **Python**, and **Jenkins** to fully automate repetitive DevOps workflows through natural language.

Instead of spending 30–45 minutes manually deploying an application, you type one command:

```text
deploy all
```

The agent understands the intent, shows you the execution plan, waits for your confirmation, and orchestrates the entire deployment — from starting the database to printing the live URL.

> **Disclaimer**
> This is a personal portfolio project built to demonstrate AI-assisted DevOps automation.
> It is not intended for production use without further hardening.

---

# 🎬 Demo

<p align="center">
<img src="assets/demo.gif" width="100%">
</p>

---

# 🚀 What Can It Do?

The agent automates the complete deployment lifecycle of a 3-tier AWS application:

**Infrastructure Management**
- Start and stop AWS EC2 instances
- Start and stop Amazon RDS databases
- Enable and disable CloudFront distributions
- Display live infrastructure status dashboard

**Deployment Automation**
- SSH into EC2 instances automatically
- Restart Docker and Nginx services
- Verify running containers via `docker ps`
- Update Jenkins credentials dynamically with new backend IP
- Trigger Jenkins freestyle pipelines via REST API
- Monitor builds in real time until completion
- Print live CloudFront URL on successful deployment

**Safety & Rollback**
- Confirm before every write or destructive action
- Ctrl+C triggers full infrastructure rollback automatically
- Stops Jenkins builds, EC2 instances, RDS, and disables CloudFront

**AI Knowledge Assistant**
- Answer any DevOps, AWS, Docker, Kubernetes, or Terraform question
- Powered by Groq's Llama 3.3 70B — responses in under 1 second

---

# 🏗 Architecture

<p align="center">
<img src="assets/architecture.png" width="95%">
</p>

---

# 🧠 How the AI Works

<p align="center">
<img src="assets/workflow.png" width="90%">
</p>

The agent is built on two independent layers.

## Layer 1 — Natural Language Understanding (Groq LLM)

Every user input is sent to Groq's Llama 3.3 70B model with a structured system prompt. The model identifies the intent and returns a JSON action object.

```text
User: "deploy frontend"
```

```json
{ "type": "deploy", "target": "frontend" }
```

```text
User: "stop all"
```

```json
{ "type": "stop", "target": "all" }
```

```text
User: "what is the difference between ECS and EKS?"
```

```json
{ "type": "general", "answer": "ECS is AWS-native container orchestration..." }
```

## Layer 2 — Deterministic Execution (Python + AWS)

Python receives the JSON action and routes it to the correct function — no ambiguity, no hallucination risk. The AI handles **understanding**, Python handles **execution**.
---

# 🔄 Deployment Workflow

<p align="center">
<img src="assets/deployment-workflow.png" width="95%">
</p>

When you run `deploy all`, the agent executes this sequence automatically:

```text
Start RDS → wait until available (~2 mins)
      ↓
Start Backend EC2 → wait until running
      ↓
SSH into Backend EC2
      ↓
Restart Docker + Nginx
      ↓
Verify containers via docker ps
      ↓
Capture backend public IP
      ↓
Update Jenkins credential (REACT_APP_API_URL) via Groovy Script Console
      ↓
Start Jenkins EC2 → SSH in → memory fix → restart Jenkins
      ↓
Enable CloudFront distribution
      ↓
Trigger Jenkins freestyle pipeline
      ↓
Monitor build in real time
      ↓
✅ Print live CloudFront URL
```

**Why this order matters:**
- RDS must be available before the backend app starts — otherwise DB connection fails
- Backend IP must be captured before updating Jenkins — otherwise frontend calls wrong URL
- Jenkins credential must be updated before build — otherwise React bakes wrong IP into bundle
- CloudFront must be enabled before build finishes — otherwise CDN serves stale content

---

# 🤖 AI Reasoning

<p align="center">
<img src="assets/reasoning.png" width="90%">
</p>

Rather than executing arbitrary shell commands from user input (which would be dangerous), the LLM maps natural language to **predefined, safe infrastructure operations**.

This design ensures:
- No unintended actions — AI can only trigger what's explicitly coded
- No hallucinated AWS calls — execution is deterministic Python, not AI-generated code
- Full auditability — every action is logged to terminal in real time

---

# 📸 Screenshots

## Infrastructure Status Dashboard

<p align="center">
<img src="assets/status.png" width="95%">
</p>

On startup, the agent scans your AWS account and displays live status of every resource with 🟢🔴 indicators. Type `status` anytime to refresh.

---

## Automated Deployment

<p align="center">
<img src="assets/deployment.png" width="95%">
</p>

The agent shows the full execution plan before proceeding, updates Jenkins credentials with the new backend IP, triggers the pipeline, and monitors it live.

---

## Jenkins Pipeline Monitoring

<p align="center">
<img src="assets/jenkins.png" width="95%">
</p>

Build progress is polled every 10 seconds. On failure, the last 50 lines of console output are fetched and displayed automatically — no need to open Jenkins manually.

---

## DevOps Knowledge Assistant

<p align="center">
<img src="assets/assistent-demo.png" width="95%">
</p>

Ask any DevOps question in plain English. The same agent that deploys your infrastructure can also explain Kubernetes scheduling, Terraform modules, or AWS pricing — without switching tools.

---

# ✨ Features Summary

| Category | Features |
|---|---|
| Infrastructure | EC2 lifecycle, RDS lifecycle, CloudFront enable/disable, status dashboard |
| Deployment | Backend deploy, frontend deploy, full stack deploy, Jenkins automation |
| SSH Automation | Docker restart, Nginx restart, container verification, Jenkins memory fix |
| Monitoring | Live build monitoring, deployment progress, failure log fetch |
| Safety | Write confirmation, Ctrl+C rollback, error handling, cleanup |
| AI Assistant | DevOps Q&A, AWS questions, general cloud engineering knowledge |

---

# 🛠 Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| AI / LLM | Groq API — Llama 3.3 70B (free tier) |
| Cloud SDK | boto3 (EC2, RDS, S3, CloudFront, CloudWatch) |
| SSH | Paramiko |
| CI/CD | Jenkins (REST API + Groovy Script Console) |
| Containers | Docker + Docker Compose |
| Reverse Proxy | Nginx |
| CDN | AWS CloudFront |
| Database | Amazon RDS PostgreSQL |
| Frontend Hosting | AWS S3 + CloudFront |

---

# 📂 Repository Structure

```text
devops-ai-agent/
├── assets/                    # Screenshots and diagrams
│   ├── banner.png
│   ├── architecture.png
│   ├── workflow.png
│   ├── deployment-workflow.png
│   ├── status.png
│   ├── deployment.png
│   ├── jenkins.png
│   ├── assistent-demo.png
│   └── demo.gif
├── agent.py                   # Main AI agent — all logic
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
├── .gitignore                 # Excludes .env and .pem
├── LICENSE
└── README.md
```

---

# ⚙ Installation

**1. Clone the repository**
```bash
git clone https://github.com/Sudipto-Acharya/devops-ai-agent.git
cd devops-ai-agent
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure environment**
```bash
cp .env.example .env
# Open .env and fill in your values
```

**4. Run the agent**
```bash
python agent.py
```

---

# 🔐 Configuration

All configuration is done via `.env` — no credentials are hardcoded in the source code.

```env
GROQ_API_KEY=your_groq_api_key
AWS_REGION=us-east-1
BACKEND_EC2_ID=i-xxxxxxxxxxxxxxxxx
JENKINS_EC2_ID=i-xxxxxxxxxxxxxxxxx
JENKINS_JOB_NAME=your_jenkins_job_name
JENKINS_USER=your_jenkins_username
JENKINS_API_TOKEN=your_jenkins_api_token
JENKINS_SSH_USER=ec2-user
BACKEND_SSH_USER=ec2-user
SSH_KEY_PATH=/path/to/your/login-key.pem
RDS_INSTANCE_ID=your_rds_identifier
CLOUDFRONT_DIST_ID=your_distribution_id
CLOUDFRONT_DOMAIN=https://your_cloudfront_domain
```

Get your free Groq API key at [console.groq.com](https://console.groq.com)

---

# 🔒 Security

- All credentials stored in `.env` — never committed to Git
- SSH private keys excluded via `.gitignore`
- Jenkins credentials managed via Jenkins Credentials Store — never in code
- Every write/destructive operation requires explicit `yes` confirmation
- Ctrl+C triggers graceful rollback — no orphaned AWS resources

---

# 🗺 Roadmap

Planned improvements:

- [ ] Kubernetes (EKS) support
- [ ] Terraform plan/apply automation
- [ ] GitHub Actions pipeline triggering
- [ ] Slack/Discord deployment notifications
- [ ] CloudWatch alarm auto-remediation
- [ ] Infrastructure drift detection
- [ ] Web dashboard UI (React)
- [ ] Voice command support
- [ ] Multi-environment support (dev/staging/prod)

---

# 📚 What I Learned Building This

- AWS SDK (boto3) — EC2, RDS, CloudFront, S3, CloudWatch APIs
- Jenkins REST API and Groovy Script Console for credential automation
- SSH automation with Paramiko — remote command execution
- Infrastructure orchestration — correct startup/shutdown ordering
- Natural language intent parsing with structured LLM outputs
- Designing safe, deterministic execution layers around AI models
- Signal handling in Python — Ctrl+C graceful rollback
- Environment variable management and secrets hygiene

---

# 👨‍💻 Author

**Sudipto Acharya** — DevOps Engineer

[![GitHub](https://img.shields.io/badge/GitHub-Sudipto--Acharya-black?logo=github)](https://github.com/Sudipto-Acharya)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-sudipto--acharya-blue?logo=linkedin)](https://linkedin.com/in/sudipto-acharya-8a3027258)
[![Portfolio](https://img.shields.io/badge/Portfolio-sudipto--acharya.vercel.app-green)](https://sudipto-acharya.vercel.app)
[![Medium](https://img.shields.io/badge/Medium-@sudiptoacharya-black?logo=medium)](https://medium.com/@sudiptoacharya)

---

# ⭐ Support

If you found this project useful or interesting, consider giving it a ⭐ on GitHub.

Feedback, suggestions, and contributions are always welcome — open an issue or reach out directly.

