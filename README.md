# MIZAN | ميزان

**An Arabic-first news verification and AI-generated media detection platform**  
University of Jordan · Computer Engineering Graduation Project · 2026

MIZAN is a collaborative graduation project that helps Arabic-speaking users assess potentially misleading news and synthetic media. It combines Arabic-language classification with evidence retrieval and semantic matching, while offering separate AI-generated image and video detection tools. Users can submit text, an article URL, an image, or a short video. A companion browser extension provides a verification shortcut directly on X (Twitter).

> **Research prototype, not a certified fact-checking service.** Automated scores are decision-support signals, not proof that a claim is true or false. Some trusted-source integration was difficult to operate reliably during the graduation demonstration; manually populated news records and demonstration values were used to show the intended workflow. See [Limitations](#limitations-and-demo-disclosure).

## What MIZAN does

| Feature | Description |
| --- | --- |
| Arabic news verification | Classifies headlines and articles, retrieves related reporting, and combines multiple evidence signals into a credibility assessment. |
| Article URL analysis | Extracts article text from a submitted URL and routes it through the news pipeline. |
| AI-generated image detection | Uses an EfficientNet-B0 + ResNet-50 ensemble to distinguish synthetic images from real photographs. |
| Video analysis | Samples video frames, runs the image ensemble on selected frames, and aggregates predictions. |
| OCR for news screenshots | Extracts Arabic/English text from an uploaded image and submits the extracted text to the **news** verification pipeline; this is separate from synthetic-image detection. |
| X browser extension | Adds a MIZAN verification control to posts on X; the extension calls the **same Flask backend** as the website. |
| Review and administration | The documented application includes a SQLite-backed result cache and administrative/community review functionality. |

## Architecture

```text
Web UI (Arabic / English)          X (Twitter) browser extension
              \                    /
               \                  /
                   Flask REST API
                         |
       +-----------------+------------------+
       |                 |                  |
  News verification  Image detection    Video detection
       |                 |                  |
  AraBERT (short/long) EfficientNet-B0   Frame selection
       |             + ResNet-50           + CNN ensemble
  MiniLM similarity
       |
  Trusted-source retrieval / matching
       |
  Weighted evidence fusion
       |
  Credibility score and supporting information
                         |
                 SQLite result cache

  Screenshot OCR --> extracted text --> News verification
```

### Arabic news verification

1. Normalize Arabic text and select the **short-text** AraBERT v02 model for inputs under 20 words or the **long-text** model for longer articles.
2. Retrieve potentially relevant news from configured sources and compare it with the submitted claim using multilingual **MiniLM** sentence embeddings.
3. Combine three signals: **AI classifier output**, **semantic similarity**, and **independent source corroboration**. The documented scoring weights adapt to input length.
4. Return an explainable credibility assessment with a score and available source information. The documented categories are **Real / Verified (70–100%)**, **Suspicious (40–69%)**, and **Likely Fake (below 40%)**.

These categories describe the prototype's scoring rules; they are **not guarantees of factual truth**. Source retrieval depends on external services and site accessibility.

### Image and video detection

The image component uses **EfficientNet-B0** and **ResNet-50**, trained from scratch for binary classification of AI-generated versus real images. The documented inference pipeline includes resizing, normalization, test-time augmentation, and ensemble aggregation.

The video pipeline selects representative and scene-change frames, classifies them with the image ensemble, and combines their outputs with attention to frame sharpness. It assesses **visual synthetic-media cues**, not whether a video's spoken or written claims are factually correct.

### OCR and browser integration

For screenshots containing written news, OCR extracts text that can be checked through the Arabic news pipeline. The documentation describes EasyOCR, PaddleOCR, and Tesseract-based processing, with optional dependencies and fallbacks.

The X extension adds a verification action alongside posts and sends the post text to the local Flask service. The extension is a **client of the existing backend**, not a separate prediction system. Extension source files must be included separately for a complete distributable extension.

## Reported research results

The following are **model-level evaluation results reported in the graduation documentation**, not an end-to-end real-world fact-checking accuracy claim:

| Evaluation | Reported result |
| --- | --- |
| Selected AraBERT v02 long-text classifier | **93.4% accuracy**, **93.3% F1** in the reported evaluation |
| Image ensemble (EfficientNet-B0 + ResNet-50) | **93.77% accuracy**, **93.76% macro F1** on a balanced held-out set of **12,000 images** (6,000 real / 6,000 AI-generated) |

The report describes **30,000 balanced labeled Arabic news articles** (15,000 credible / 15,000 not credible) for the text-classification dataset. These dataset and benchmark figures should not be confused with the amount of news available for live source verification.

## Repository layout

```text

MIZAN/
├── backend1.py
├── MIZAN_extras.py
├── download_models.py
├── extension/
│   ├── manifest.json
│   ├── content.js
│   ├── popup.html
│   └── popup.js
├── templates/
│   └── frontendA.html
├── requirements.txt
├── requirements-optional.txt
├── .gitignore
└── README.md


The structure above describes the GitHub preparation copy. Model weights and large model directories are intentionally not committed.

## Local setup (Windows / PowerShell)

**Prerequisites:** Python 3.12, sufficient disk space for multiple large model downloads, and an internet connection for initial setup.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Optional OCR/browser-related packages:

```powershell
python -m pip install -r requirements-optional.txt
```

Download the trained model files from the team's Hugging Face repository:

```powershell
python download_models.py
```

Model source: [LojainOS/MIZAN on Hugging Face](https://huggingface.co/LojainOS/MIZAN/tree/main).

Configure any optional external integrations through **environment variables** (do not commit credentials):

```dotenv
SERPER_API_KEY=
GEMINI_API_KEY=
MIZAN_RUN_SCRAPER=0
MIZAN_ADMIN_PASSWORD=
```

Start the application:

```powershell
python backend1.py
```

Visit **http://127.0.0.1:5000**.


**Setup verification status:** Dependencies were successfully installed in a fresh Python 3.12 virtual environment. The Flask application started successfully, and both Arabic news-text analysis and AI-generated image detection were tested locally. The X browser extension was also tested with the local Flask backend. Model files were already available during these tests; a fresh download of all model artifacts has not yet been independently verified. Some optional OCR features may require additional system packages or configuration.


## X Browser Extension Setup

The extension is designed for local use with the MIZAN Flask backend.

1. Start the Flask backend using `python backend1.py`.
2. Open Google Chrome and navigate to `chrome://extensions`.
3. Enable **Developer mode**.
4. Select **Load unpacked**.
5. Choose the `extension` folder from this repository.
6. Open X (Twitter) and use the MIZAN verification control on a post.

The extension communicates with the local backend at `http://127.0.0.1:5000`. Keep the Flask server running while using it.

**Note:** The extension is a research prototype and is not published on the Chrome Web Store.

## Limitations and demo disclosure

- **Trusted-source access:** The intended architecture uses live retrieval from news outlets, aggregators, and APIs. During the graduation demonstration, reliable integration with several trusted Jordanian sources was difficult; manually seeded articles and demonstration values were used to present the verification workflow. Do **not** interpret seeded evidence or scores as independently verified live reporting.
- **News classification:** A model's confidence score does not establish truth. Novel events, satire, short claims, limited source coverage, and dialectal variation can lead to misleading results.
- **Synthetic-media detection:** Performance can degrade on newer generators, unfamiliar image distributions, low-quality footage, and edited media.
- **OCR:** Accuracy depends on image resolution, typography, and background complexity.
- **Deployment:** The current configuration is intended for local research/demo use, not a public production service. External APIs, access controls, input handling, rate limits, and secrets require a deployment-specific security review.

## Team and contributions

MIZAN was developed collaboratively at **The University of Jordan**, Department of Computer Engineering, under the supervision of **Dr. Samah Rahamneh**.

**Project team:** Haneen Omar Qamar, Lojain Osama Salameh, and Ammar Awad Laimoon.

**Ammar's contributions** included:

- Training and evaluating the **EfficientNet-B0** and **ResNet-50** models used for AI-generated image detection, and contributing to their integration into the system.
- Contributing to **backend implementation and integration**.
- Proposing the **manually seeded demonstration-data approach** when access to trusted-source APIs and websites became a blocker close to the project deadline.

The web frontend, X extension, and other project components were developed collaboratively by the team; the above bullets do not claim sole ownership of those components.

## Academic context

This README summarizes the team's graduation report, flowchart, and presentation. For methodology, model comparisons, and evaluation details, refer to the original project documentation. The model artifacts remain hosted in the team's Hugging Face repository.
