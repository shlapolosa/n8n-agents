# TOGAF Enterprise Delivery Workflow

An n8n workflow that automates enterprise architecture documentation using TOGAF ADM methodology, AI agents, and KubeVela OAM deployment specifications.

> **Reference**: This project is inspired by and references the concepts from [this YouTube video](https://www.youtube.com/watch?v=d3bWvva6ucw&t=306s) on enterprise architecture automation.

## Overview

This workflow provides an end-to-end solution for:
- Creating microservice repositories via Slack bot integration
- Generating comprehensive TOGAF architecture documentation using AI agents
- Producing ArchiMate 3.1 XML models for each architecture domain
- Creating KubeVela OAM deployment specifications
- Automatically committing all artifacts to GitHub

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     TOGAF Enterprise Delivery Workflow                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Chat Input → Quick Parse → Slack /microservice → Wait for Repo             │
│                                        ↓                                     │
│                              [Slack Listener Workflow]                       │
│                                        ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        AI Agent Pipeline                             │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │  Orchestrator → BA Agent ──────┬──→ Business Owner → Bus. Architect │    │
│  │                 Compliance Agent┘                    CTO Agent      │    │
│  │                                                          ↓          │    │
│  │  App Architect → Infra Architect → PM Agent → Solution Architect    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                        ↓                                     │
│  Parse Context → Commit to GitHub (docs/) → Slack Notification → Done       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Prerequisites

- **n8n** (self-hosted or cloud) - v1.0+
- **OpenAI API** account with GPT-4o access
- **GitHub** account with personal access token
- **Slack** workspace with:
  - OAuth2 app configured
  - Microservice bot (`vcluster-bot`) installed
  - Access to `#all-internal-developer-platform` channel

## Files Included

| File | Description |
|------|-------------|
| `togaf-agents-current-v2.json` | Main TOGAF workflow with Slack integration |
| `n8n_pipe.py` | OpenWebUI Pipe function for real-time status updates |

## Environment Variables

A `.env.example` file is included with all required variables. Copy it and fill in your values:

```bash
cp .env.example .env
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `N8N_WEBHOOK_URL` | Your n8n instance base URL | `https://your-instance.app.n8n.cloud` |
| `SLACK_CLIENT_ID` | Slack OAuth2 App Client ID | `9172684301539.9181628633154` |
| `SLACK_CLIENT_SECRET` | Slack OAuth2 App Client Secret | `e37b9111570448e3fd16ed8894da4719` |
| `SLACK_SIGNING_SECRET` | Slack App Signing Secret | `1f50ac1d5e5c39eb9bf00dad682a4141` |
| `SLACK_CHANNEL_ID` | Channel ID for microservice bot | `C0123456789` |
| `GITHUB_OWNER` | GitHub username/org for repos | `shlapolosa` |
| `GITHUB_TOKEN` | GitHub Personal Access Token | `ghp_xxxx...` |
| `OPENAI_API_KEY` | OpenAI API Key | `sk-xxxx...` |

## Setup Instructions

### Step 1: Configure n8n Environment Variables (Hosted Solution)

For **n8n Cloud** or other hosted solutions where you don't have container access:

#### Method 1: Using n8n Variables (Recommended)

n8n has a built-in Variables feature that works like environment variables:

1. In n8n, go to **Settings** (gear icon) → **Variables**
2. Click **Add Variable** for each of the following:

| Name | Value |
|------|-------|
| `N8N_WEBHOOK_URL` | `https://your-instance.app.n8n.cloud` |
| `SLACK_CHANNEL_ID` | Your Slack channel ID |
| `GITHUB_OWNER` | `shlapolosa` |

3. In your workflow, reference these using: `{{ $vars.VARIABLE_NAME }}`

#### Method 2: Using Expressions in Nodes

If Variables aren't available, you can hardcode values directly in nodes or use n8n's expression syntax.

#### Accessing Variables in Workflows

In any node, you can reference variables using:

```javascript
// n8n Variables (Settings → Variables)
{{ $vars.N8N_WEBHOOK_URL }}
{{ $vars.SLACK_CHANNEL_ID }}

// Environment variables (if available)
{{ $env.N8N_WEBHOOK_URL }}
{{ $env.SLACK_CHANNEL_ID }}
```

#### For the Wait Node Webhook URL

The workflow uses this pattern for the resume webhook:
```
{{ $vars.N8N_WEBHOOK_URL }}/webhook-waiting/togaf-resume-{{ $json.repositoryName }}
```

> **Note**: The `N8N_WEBHOOK_URL` should be your n8n instance URL without a trailing slash, e.g., `https://your-name.app.n8n.cloud`

### Step 2: Create Slack OAuth2 Credentials

1. Go to [Slack API Apps](https://api.slack.com/apps)
2. Create a new app or use existing one
3. Navigate to **OAuth & Permissions**
4. Add the following scopes:
   - `chat:write` - Send messages
   - `channels:read` - Read channel info
   - `channels:history` - Read message history
5. Install the app to your workspace
6. Copy the **Bot User OAuth Token**

In n8n:
1. Go to **Settings → Credentials → Add Credential**
2. Select **Slack OAuth2 API**
3. Enter your Client ID and Client Secret
4. Click **Connect** to authorize

### Step 3: Create OpenAI Credentials

1. Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Create a new API key
3. In n8n: **Settings → Credentials → Add Credential → OpenAI API**
4. Enter your API key

### Step 4: Create GitHub Credentials

1. Go to [GitHub Personal Access Tokens](https://github.com/settings/tokens)
2. Generate a new token (classic) with scopes:
   - `repo` - Full control of private repositories
3. In n8n: **Settings → Credentials → Add Credential → GitHub API**
4. Enter your token

### Step 5: Get Slack Channel ID

1. Open Slack
2. Right-click on `#all-internal-developer-platform` channel
3. Select **View channel details**
4. Scroll down to find the **Channel ID** (starts with `C`)
5. Copy this ID

### Step 6: Import Workflows

#### Import Main Workflow

1. In n8n, go to **Workflows → Import from File**
2. Select `togaf-workflow-with-slack.json`
3. Open the imported workflow

#### Import Slack Listener Workflow

1. Import `togaf-slack-listener.json`
2. This workflow must be **activated** and running

### Step 7: Configure Placeholders

In the **main workflow**, find and replace these placeholders:

| Placeholder | Replace With | Location |
|-------------|--------------|----------|
| `SLACK_CHANNEL_ID` | Your channel ID (e.g., `C0123456789`) | Slack nodes |
| `SLACK_CREDENTIAL_ID` | Auto-populated after connecting | Slack nodes |
| `OPENAI_CREDENTIAL_ID` | Auto-populated after connecting | OpenAI nodes |
| `GITHUB_CREDENTIAL_ID` | Auto-populated after connecting | GitHub nodes |
| `HEADER_AUTH_CREDENTIAL_ID` | Auto-populated after connecting | Webhook Trigger |

In the **Slack Listener workflow**, replace:

| Placeholder | Replace With |
|-------------|--------------|
| `SLACK_CHANNEL_ID` | Same channel ID as above |
| `SLACK_CREDENTIAL_ID` | Same Slack credential |

### Step 8: Activate Workflows

1. **First**, activate the **TOGAF Slack Listener** workflow
   - This must be running to catch microservice bot responses
2. **Then**, activate the **main TOGAF workflow**

## OpenWebUI Integration

This workflow supports integration with OpenWebUI via a custom Pipe function that provides real-time status updates during workflow execution.

### Data Flow Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            OPENWEBUI + N8N DATA FLOW                          │
└──────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐     ┌─────────────────────────────────────────────────────────┐
│  OPENWEBUI  │     │                      N8N WORKFLOW                        │
│             │     │                                                          │
│  User types │     │  ┌─────────────────────────────────────────────────┐    │
│  request    │     │  │         PATH 1: WEBHOOK (Synchronous)           │    │
│      │      │     │  │                                                 │    │
│      ▼      │     │  │  Webhook ──► Service Name Agent ──► Parse      │    │
│ ┌─────────┐ │     │  │     │              │                   │       │    │
│ │  Pipe   │─┼─────┼──┼─────┘              ▼                   ▼       │    │
│ │Function │ │ POST│  │            Store Context ──► Create Repo (Slack)│    │
│ └────┬────┘ │     │  │                   │                            │    │
│      │      │     │  │                   ▼                            │    │
│      │      │     │  │         Return executionId + statusUrl         │    │
│      │      │     │  └─────────────────────────────────────────────────┘    │
│      │      │     │                                                          │
│      │      │     │  ┌─────────────────────────────────────────────────┐    │
│      │      │     │  │         PATH 2: SLACK EVENT (Async)             │    │
│      │      │     │  │                                                 │    │
│      │      │     │  │  Slack Event ──► Retrieve Context               │    │
│      │      │     │  │       │                │                        │    │
│      │      │     │  │       ▼                ▼                        │    │
│      │      │     │  │  ┌──────────────────────────────────────┐      │    │
│      │      │     │  │  │          AI AGENT PIPELINE           │      │    │
│      │      │     │  │  │                                      │      │    │
│      │      │     │  │  │  Phase 1: BA Agent + Compliance      │      │    │
│      │      │     │  │  │      │    ▼ Update Status Storage    │      │    │
│      │      │     │  │  │  Phase 2: Business Architecture      │      │    │
│ ┌────┴────┐ │     │  │  │      │    ▼ Update Status Storage    │      │    │
│ │ Poll    │ │     │  │  │  Phase 3: Technical Architecture     │      │    │
│ │ Status  │─┼─────┼──┼──┼──────┼────▼ Update Status Storage    │      │    │
│ │ (5 sec) │ │ GET │  │  │  Phase 4: Commit to GitHub           │      │    │
│ └────┬────┘ │     │  │  │      │    ▼ Update Status Storage    │      │    │
│      │      │     │  │  │  Phase 5: Complete                   │      │    │
│      │      │     │  │  └──────────────────────────────────────┘      │    │
│      │      │     │  └─────────────────────────────────────────────────┘    │
│      ▼      │     │                                                          │
│ ┌─────────┐ │     │  ┌─────────────────────────────────────────────────┐    │
│ │ Status  │ │     │  │           STATUS WEBHOOK (GET)                  │    │
│ │ Updates │◄┼─────┼──┼───  /webhook/togaf-status?executionId=xxx      │    │
│ │ in Chat │ │ JSON│  │                      │                          │    │
│ └─────────┘ │     │  │                      ▼                          │    │
│      │      │     │  │   Returns: {phase, message, progress, done}     │    │
│      ▼      │     │  └─────────────────────────────────────────────────┘    │
│  Final     │     │                                                          │
│  Response   │     │                                                          │
└─────────────┘     └──────────────────────────────────────────────────────────┘
```

### Why Polling (Not Webhooks/Callbacks)

The architecture uses **polling** instead of webhook callbacks because:

1. **Chat Context Persistence**: If a user switches chats while waiting, callbacks can't inject responses into the original chat context
2. **Connection Control**: The Pipe function maintains the HTTP connection, ensuring updates always appear in the correct conversation
3. **UX Consistency**: User sees continuous "thinking" indicator with progressive status updates

### OpenWebUI Configuration

#### Step 1: Install the Pipe Function

1. In OpenWebUI, go to **Admin Panel → Functions**
2. Click **Create Function**
3. Copy the contents of `n8n_pipe.py` into the function editor
4. Save the function

#### Step 2: Configure Valves

After saving, configure the function's valves:

| Valve | Description | Example Value |
|-------|-------------|---------------|
| `n8n_url` | Main workflow webhook URL | `https://n8n.your-domain.com/webhook/togaf-architect-v2` |
| `n8n_status_url` | Status polling endpoint | `https://n8n.your-domain.com/webhook/togaf-status` |
| `n8n_bearer_token` | Authentication token | `testAuth` |
| `input_field` | JSON field for user input | `chatInput` |
| `response_field` | JSON field for response | `output` |
| `poll_interval` | Seconds between polls | `5.0` |
| `max_poll_time` | Maximum wait time (seconds) | `600.0` |
| `emit_interval` | Minimum seconds between status UI updates | `2.0` |
| `enable_status_indicator` | Show status in UI | `true` |

#### Step 3: Enable as Model

1. Go to **Admin Panel → Functions**
2. Find your N8N Pipe function
3. Toggle **Enable** to make it appear as a model in the chat UI

#### Step 4: Use in Chat

1. Start a new chat in OpenWebUI
2. Select "N8N Pipe" (or your function name) as the model
3. Type your TOGAF project request
4. Watch real-time status updates as the workflow progresses

### N8N Workflow Configuration for OpenWebUI

The n8n workflow requires these components for OpenWebUI integration:

#### 1. Status Webhook Node

Create a webhook to handle status polling:

- **Path**: `/webhook/togaf-status`
- **Method**: GET
- **Authentication**: Header Auth (same as main webhook)
- **Response**: JSON from static data storage

```javascript
// Status Handler Code Node
const staticData = $getWorkflowStaticData('global');
const executionId = $input.first().json.query.executionId;
const status = staticData.executions?.[executionId];

if (!status) {
  return { json: { error: 'Execution not found', executionId, done: true } };
}

return { json: status };
```

#### 2. Execution ID Generation

In the "Store Context" node, generate a unique execution ID:

```javascript
const executionId = `togaf-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

// Store in static data
const staticData = $getWorkflowStaticData('global');
staticData.executions = staticData.executions || {};
staticData.executions[executionId] = {
  executionId,
  phase: 'starting',
  phaseNumber: 0,
  totalPhases: 5,
  message: "🚀 Starting TOGAF workflow...",
  progress: 5,
  done: false,
  result: null
};
```

#### 3. Status Update Nodes

After each phase, update the status storage:

```javascript
// Example: After Phase 1 (Requirements)
const staticData = $getWorkflowStaticData('global');
const executionId = $('Store Context').first().json.executionId;

staticData.executions[executionId] = {
  ...staticData.executions[executionId],
  phase: 'requirements',
  phaseNumber: 1,
  message: "🔍 Phase 1: Requirements Analysis\n\n✅ Context established\n🔧 Analyzing requirements...",
  progress: 20,
  updatedAt: new Date().toISOString()
};
```

#### 4. Phase Status Messages

| Phase | Progress | Message |
|-------|----------|---------|
| 0 | 5% | 🚀 Starting TOGAF workflow... |
| 1 | 20% | 🔍 Phase 1: Requirements Analysis |
| 2 | 40% | 📈 Phase 2: Business Architecture |
| 3 | 60% | ⚙️ Phase 3: Technical Architecture |
| 4 | 80% | 💾 Phase 4: Committing Artifacts |
| 5 | 100% | ✅ TOGAF Enterprise Architecture Complete |

### Status Cleanup (Memory Management)

Add TTL cleanup to prevent memory bloat in n8n:

```javascript
// Add to any status update node
const staticData = $getWorkflowStaticData('global');
const ONE_HOUR = 60 * 60 * 1000;
const now = Date.now();

if (staticData.executions) {
  for (const [id, exec] of Object.entries(staticData.executions)) {
    if (exec.updatedAt && (now - new Date(exec.updatedAt).getTime()) > ONE_HOUR) {
      delete staticData.executions[id];
    }
  }
}
```

---

## Usage

### Entry Points

The workflow supports three entry points:

#### 1. OpenWebUI (Recommended for End Users)

Use the OpenWebUI Pipe function for the best user experience with real-time status updates:

1. Open OpenWebUI
2. Select "N8N Pipe" as the model
3. Enter your project requirements:

```
Build a patient appointment scheduling system for a healthcare clinic.
The system should allow patients to book appointments online, send
reminders, and integrate with the clinic's existing EHR system.
```

4. Watch real-time status updates in the chat as the workflow progresses

#### 2. Chat Trigger (n8n Interactive Testing)

1. Open the n8n Chat interface (click **Chat** button on the workflow)
2. Enter your project requirements, for example:

```
Build a patient appointment scheduling system for a healthcare clinic.
The system should allow patients to book appointments online, send
reminders, and integrate with the clinic's existing EHR system.
Key stakeholders: Clinic administrators, doctors, patients, IT team.
```

3. The workflow will display progress messages as it runs in the chat

#### 3. Webhook Trigger (Programmatic API Integration)

For programmatic access, use the webhook endpoint:

```bash
# Using X-API-Key header (configure in Header Auth credential)
curl -X POST https://your-n8n.app.n8n.cloud/webhook/togaf-delivery \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key-here" \
  -d '{
    "chatInput": "Build a patient appointment scheduling system for healthcare..."
  }'
```

**Setting up Webhook Authentication:**

1. Go to **Settings → Credentials → Add Credential**
2. Select **Header Auth**
3. Configure:
   - **Name**: `TOGAF API Auth`
   - **Header Name**: `X-API-Key` (or `Authorization`)
   - **Header Value**: Your chosen API key/token
4. Save and link to the Webhook Trigger node

**Webhook Response Format:**

```json
{
  "summary": "TOGAF Enterprise Architecture workflow completed!...",
  "repositoryUrl": "https://github.com/shlapolosa/patient-scheduling-123456",
  "statusLog": [
    "🚀 Starting TOGAF Enterprise Architecture Process",
    "✅ Repository Created Successfully",
    "📋 Phase 2: Requirements & Compliance Analysis",
    "📊 Phase 3: Business Architecture",
    "🏗️ Phase 4: Technical Architecture",
    "📝 Phase 5: Committing Artifacts"
  ]
}
```

### Progress Messages

The workflow displays progress messages as it runs:
   - 🚀 Starting TOGAF Enterprise Architecture Process
   - ✅ Repository Created Successfully
   - 📋 Phase 2: Requirements & Compliance Analysis
   - 📊 Phase 3: Business Architecture
   - 🏗️ Phase 4: Technical Architecture
   - 📝 Phase 5: Committing Artifacts
   - ✅ Workflow Complete

### Output Artifacts

The workflow commits the following files to `docs/` in your new repository:

| File | Description |
|------|-------------|
| `docs/architecture/requirements-model.xml` | Stakeholder requirements (ArchiMate 3.1) |
| `docs/architecture/compliance-model.xml` | Regulatory compliance mapping |
| `docs/architecture/business-canvas-model.xml` | Business Model Canvas |
| `docs/architecture/business-architecture-model.xml` | Business processes & capabilities |
| `docs/architecture/tech-recommendations-model.xml` | Technology recommendations |
| `docs/architecture/application-architecture-model.xml` | Application components |
| `docs/architecture/infrastructure-architecture-model.xml` | Infrastructure architecture |
| `docs/architecture/implementation-plan-model.xml` | Implementation roadmap |
| `docs/deployment/application.oam.yaml` | KubeVela OAM deployment spec |
| `docs/PRD.md` | Product Requirements Document |

## KubeVela OAM Output

The Solution Architect Agent generates a KubeVela OAM Application YAML file using only the component definitions available in your platform:

### Available Components
- `webservice` - Knative-based web services
- `identity-service` - Identity/Auth services
- `graphql-gateway` - GraphQL Federation gateway
- `rasa-chatbot` - Conversational AI
- `realtime-platform` - IoT/Realtime data platform
- `camunda-orchestrator` - BPMN workflow orchestration
- `kafka` - Message streaming
- `redis` - Caching layer
- `mongodb` - Document database
- `postgresql` - Relational database
- `vcluster` - Virtual Kubernetes clusters
- `clickhouse` - Analytics database
- `neon-postgres` - Serverless Postgres
- `auth0-idp` - Auth0 identity provider

### Available Traits
- `ingress` - HTTP routing with TLS
- `autoscaler` - Horizontal pod autoscaling
- `kafka-producer` - Kafka producer configuration
- `kafka-consumer` - Kafka consumer configuration

## Workflow Architecture Details

### AI Agents

| Agent | Role | Output |
|-------|------|--------|
| **Orchestrator** | Parses requirements, creates project context | JSON context |
| **Business Analyst** | Requirements elicitation | ArchiMate Requirements Model |
| **Compliance Officer** | Regulatory mapping | ArchiMate Compliance Model |
| **Business Owner** | Business Model Canvas | ArchiMate Business Canvas |
| **Business Architect** | Business processes/capabilities | ArchiMate Business Architecture |
| **CTO** | Technology recommendations | ArchiMate Tech Recommendations |
| **Application Architect** | Application design | ArchiMate Application Architecture |
| **Infrastructure Architect** | Infrastructure design | ArchiMate Infrastructure Architecture |
| **Project Manager** | Implementation planning | ArchiMate Implementation Plan |
| **Solution Architect** | Final solution design | KubeVela OAM Application YAML |

### Event-Driven Pattern

The workflow uses an event-driven pattern with two workflows:

1. **Main Workflow**: Sends `/microservice create` command to Slack, then waits
2. **Listener Workflow**: Watches for "Repositories created/updated" message, extracts repo name, and resumes the main workflow via webhook

This ensures the repository exists before AI agents run, preventing race conditions.

## Troubleshooting

### Common Issues

**Workflow doesn't resume after Slack message**
- Ensure the Slack Listener workflow is **activated**
- Check that the channel ID matches in both workflows
- Verify the `N8N_WEBHOOK_URL` environment variable is set correctly

**GitHub commits fail**
- Verify your GitHub token has `repo` scope
- Check that the repository was created successfully
- Ensure the owner (`shlapolosa`) matches your GitHub username

**OpenAI errors**
- Verify your API key is valid
- Check you have access to GPT-4o model
- Monitor your API usage limits

**Slack messages not sending**
- Verify OAuth scopes include `chat:write`
- Check the channel ID is correct
- Ensure the bot is added to the channel

### Logs

Check n8n execution logs for detailed error information:
1. Go to **Executions** in n8n
2. Find the failed execution
3. Click to view detailed logs for each node

## Customization

### Changing the AI Model

To use a different model (e.g., GPT-4 Turbo):
1. Open any OpenAI node
2. Change the `model` parameter from `gpt-4o` to your preferred model

### Modifying Agent Prompts

Each agent's behavior is controlled by its `systemMessage` parameter. Edit these to:
- Change output format
- Add domain-specific knowledge
- Modify the level of detail

### Adding New Agents

1. Add a new AI Agent node
2. Connect an OpenAI Chat Model sub-node
3. Configure the system message
4. Update the Parse Project Context code to extract the new output
5. Add a new GitHub commit node for the artifact

## License

This workflow is provided as-is for enterprise architecture automation.

## Support

For issues or questions:
- Check n8n documentation: https://docs.n8n.io
- n8n Community: https://community.n8n.io
- GitHub Issues: https://github.com/anthropics/claude-code/issues
