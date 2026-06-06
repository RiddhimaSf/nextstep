# 👣 NextStep

**A trauma-informed guide for sexual assault survivors in New York City.**

🔗 **Live at [nextstep-nyc.streamlit.app](https://nextstep-nyc.streamlit.app)**

---

## The problem

When someone experiences sexual assault, the first hour is the hardest. Existing resources — hotlines, websites, resource pages — provide information but require survivors to navigate it themselves. In a moment of shock and trauma, that navigation is often impossible.

NextStep is different. It asks the questions so survivors don't have to figure out what to ask. One step at a time, it guides them through exactly what to do — without pressure, without judgment, and without requiring them to already know what their options are.

---

## What it does

NextStep guides survivors through a structured flow based on their specific situation:

- **Are you safe right now?** — If not, shows nearest safe places with walking directions
- **Is the perpetrator still nearby?** — Routes to 911 guidance or hospital guidance accordingly
- **Nearest certified SAFE hospital** — Based on real-time location, with walking, driving, and transit times and one-tap Google Maps directions
- **What to expect at the hospital** — Step by step guidance on the forensic exam process
- **Support resources** — Legal options, counselling, financial assistance, with working links
- **AI-powered Q&A** — Survivors can ask any question and receive a compassionate, trauma-informed response

RAINN's hotline (1-800-656-4673) is visible on every single screen.

---

## How it's built

| Layer | Technology |
|-------|-----------|
| Frontend | Streamlit |
| AI layer | Anthropic Claude API |
| Location | Google Maps Geocoding API |
| Directions | Google Maps Directions API |
| Hospital data | NY State Department of Health — SAFE Designated Hospitals |
| Hosting | Streamlit Cloud |

---

## Hospital data

All 20 hospitals shown in NextStep are verified SAFE Designated Hospitals from the official [New York State Department of Health database](https://profiles.health.ny.gov/Hospital/designated_center/SAFE+Designated+Hospital). SAFE designation means the hospital has trained Sexual Assault Nurse Examiners (SANEs) available 24/7 and follows certified protocols for forensic examination and survivor care.

---

## Key design decisions

**Guided not informational** — Every existing resource gives survivors information and asks them to navigate it. NextStep makes decisions for someone who cannot make decisions right now.

**No pressure to report** — The tool never pushes survivors toward reporting to police. Reporting is presented as one option among many, always the survivor's choice.

**Forensic exam is free** — Under federal law (VAWA) survivors cannot be billed for a forensic exam. This is stated clearly and repeatedly because cost is a documented barrier to seeking care.

**Evidence kit storage** — Survivors who choose not to report are told their kit is stored for at least 6 months. They do not have to decide anything immediately.

**RAINN always visible** — The national hotline appears at the bottom of every screen regardless of where the user is in the flow.

---

## Running locally

```bash
git clone https://github.com/RiddhimaSf/nextstep.git
cd nextstep
pip install -r requirements.txt
```

Create a `.streamlit/secrets.toml` file:

```toml
ANTHROPIC_KEY = "your_anthropic_key"
GOOGLE_MAPS_KEY = "your_google_maps_key"
```

Then run:

```bash
streamlit run crisis.py
```

---

## Disclaimer

NextStep is an independent resource and is not affiliated with RAINN, Safe Horizon, NYC Well, or any other organisation listed. All organisations are referenced for informational purposes only. This tool does not constitute legal, medical, or professional advice. If you are in immediate danger please call 911.

---

## Built by

Riddhima Saraf — [ras10052@nyu.edu](mailto:ras10052@nyu.edu) — NYU Class of 2025
