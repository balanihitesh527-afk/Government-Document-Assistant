# Government-Document-Assistant
# 📄 Government Document Assistant

An AI-powered web platform that helps students and citizens prepare
scholarship and government scheme applications by identifying
potential document mismatches and missing requirements.

Built during a 6-hour hackathon by **Team Phoenix Force**.

## Problem

Applying for government schemes and scholarships often requires
multiple documents. Applicants may struggle to understand document
requirements, identify inconsistencies across certificates, or find
the correct procedure to resolve errors.

People unfamiliar with online application processes may depend on
cyber cafes or intermediaries for assistance, leading to confusion
and repeated corrections.

## Our Solution

Government Document Assistant helps users check document requirements,
identify potential mismatches, and understand issues before submitting
an application.

Users can select a supported scheme, upload documents, and review
a report highlighting detected issues and items that require manual
verification.

The platform aims to help people prepare applications more
independently. It does not replace official government services
or guarantee application approval.

## Key Features

- Scheme-wise document checklist
- Document upload and information extraction (OCR)
- Detection of potential mismatches in details such as name and date of birth
- Missing document check
- Simple explanations of detected issues
- Final report of issues and items to verify manually

## How It Works

1. Select a supported scheme.
2. Upload your documents.
3. Key details are extracted from the documents.
4. Rule-based checks compare details and find missing documents.
5. AI explains the detected issues in simple language.
6. You receive a report with items to verify before applying.

**Roles in the system:** OCR reads the documents. Rule-based validation finds mismatches and missing documents. AI explains the results; it does not decide scheme requirements.

## Tech Stack

| Part | Technology |
|---|---|
| Frontend | [FRONTEND] |
| Backend | [BACKEND] |
| OCR | [OCR TOOL] |
| AI | [AI MODEL / API] |

## Getting Started

```bash
git clone https://github.com/[USERNAME]/[REPO].git
cd [REPO]
[INSTALL COMMAND]
[RUN COMMAND]
```

Add your API key in a `.env` file (see `.env.example`). Never commit API keys.

## Demo

1. Select **[SCHEME NAME]**.
2. Upload the sample documents from `sample_data/`.
3. Review the report showing detected mismatches and missing documents.

## Limitations

- Hackathon prototype. It does not submit applications to any government portal.
- Supports a limited set of schemes: [LIST].
- OCR accuracy depends on image quality.
- Results are potential issues, not final decisions. Always confirm on the official portal.

## Privacy and Disclaimer

- Use only sample or dummy documents for testing and demos.
- [ONE LINE: how uploaded documents are handled, e.g. "Documents are processed during the session and not stored."]
- This tool provides guidance only. It does not guarantee approval of any application and is not affiliated with any government body.

## Team

**Team Phoenix Force**

