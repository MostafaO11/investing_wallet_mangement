# Investing Wallet 💰

A Streamlit-based Portfolio Management web application that uses a Net Asset Value (NAV) and Units methodology—similar to how a mutual fund operates.

This application allows multiple investors to pool their funds together. It dynamically computes individual ownership and balances securely using Google Sheets as a Single Source of Truth for logging transactions. 

## Features

- **NAV & Units Methodology:** Tracks each investor's deposits and withdrawals dynamically, issuing units to represent their share of the total portfolio fairly.
- **Transactions Log:** Uses Google Sheets as an append-only transaction history ensuring absolute transparency and data safety.
- **Dynamic KPIs:** Automatically runs real-time calculations using pandas to determine current Nav, Total Portfolio Value, Outstanding Units, and individual Profit/Loss and ROI metrics.
- **Interactive Visualizations:** Includes fully interactive dashboard charts implemented with Plotly (NAV history timeline, ownership distribution pies, and per-user performance timelines).
- **Secure Authentication:** Basic built-in form authentication utilizing Streamlit secrets.

## Operations Supported

1. **Add New Investor / Deposit:** Deposit funds. Units are purchased at the current NAV.
2. **Withdrawal:** Liquidate shares and withdraw funds based on the real-time NAV.
3. **Portfolio Revaluation:** Adjust the total current market value of the entire portfolio which universally updates the NAV for all investors.

## Tech Stack

- **[Streamlit](https://streamlit.io/):** Rapid front-end and web app execution.
- **[Pandas](https://pandas.pydata.org/):** Data manipulation and calculations.
- **[Plotly Express](https://plotly.com/python/):** Interactive charting.
- **[gspread](https://docs.gspread.org/):** Database interaction with Google Sheets.
- **Google Cloud Auth:** Service account-based authentication.

## Local Setup

### 1. Requirements

Ensure you have Python 3.9+ installed. Run the following to install the required libraries:

```bash
pip install -r requirements.txt
```

### 2. Google Sheets Configuration

1. Create a Google Sheet named **InvestingWallet**.
2. Go to Google Cloud Console, and create a Service Account. Save the generated `.json` key file.
3. Share the Google Sheet with the Service Account email created in the previous step (give it Editor access).

### 3. Add Streamlit Secrets

1. Create a `.streamlit` folder inside your project directory.
2. Inside that folder, create a `secrets.toml` file.
3. Add your simple app password and your Google Cloud JSON credentials formatted as a TOML dictionary:

```toml
app_password = "your_secure_password"

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "..."
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

### 4. Run the App

From your terminal, navigate to the directory containing `app.py` and run:

```bash
streamlit run app.py
```

## Deployment (Streamlit Community Cloud)

1. Upload `app.py`, `requirements.txt`, `README.md`, and `LICENSE` to a public or private GitHub repository.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with your GitHub account.
3. Click **New App**, select your repository, branch, and specify `app.py` as your main file path.
4. Before clicking Deploy, go to **Advanced Settings -> Secrets**.
5. Paste the exact contents of your local `.streamlit/secrets.toml` file into the remote text box and save. 
6. Deploy!

> **Warning:** Never push your `.streamlit/` folder or `secrets.toml` file to GitHub—always add `.streamlit/` to your `.gitignore` file to avoid exposing credentials.
