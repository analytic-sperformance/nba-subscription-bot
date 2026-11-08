\# Analytics Performance — NBA Telegram Bot



A Telegram bot for distributing NBA match predictions through a subscription-based access model.



\## Overview



Analytics Performance provides a Telegram interface for accessing NBA match predictions. The application manages users, subscriptions, payment receipts, and prediction file delivery.



\## Features



\- User registration and management

\- Multiple subscription plans

\- Subscription activation and expiration tracking

\- Manual payment receipt verification

\- Administrative panel

\- Subscription management by administrators

\- Broadcast messaging to active subscribers

\- CSV prediction file distribution



\## Tech Stack



\- Python

\- Aiogram 3

\- SQLite

\- Asyncio

\- python-dotenv



\## Project Structure



```text

analytics-performance/

├── bot/

│   ├── \_\_init\_\_.py

│   ├── config.py

│   ├── database.py

│   ├── states.py

│   ├── keyboards.py

│   ├── handlers.py

│   └── admin.py

├── output/

│   └── .gitkeep

├── main.py

├── requirements.txt

├── .env.example

├── .gitignore

└── README.md

```



\## Installation



\### 1. Clone the repository



```bash

git clone <repository-url>

cd analytics-performance

```



\### 2. Create a virtual environment



```bash

python -m venv .venv

```



\### 3. Activate the environment



Windows PowerShell:



```powershell

.\\.venv\\Scripts\\Activate.ps1

```



\### 4. Install dependencies



```bash

pip install -r requirements.txt

```



\### 5. Configure environment variables



Create a `.env` file based on `.env.example`.



Required variables:



| Variable | Description |

|---|---|

| BOT\_TOKEN | Telegram bot token |

| ADMIN\_ID | Administrator Telegram ID |

| SUBSCRIPTION\_DAYS | Subscription duration |

| DB\_PATH | SQLite database path |

| PREDICTION\_FILE | CSV prediction file path |



\### 6. Run the bot



```bash

python main.py

```



\## Subscription Workflow



1\. User starts the bot.

2\. User selects a subscription plan.

3\. User submits a payment receipt.

4\. Administrator reviews the receipt.

5\. Administrator approves or rejects the payment.

6\. Approved subscriptions are activated.

7\. Active subscribers can request prediction files.



\## Database



The application uses SQLite and two primary tables.



\*\*Users\*\*

\- Telegram user ID

\- Username

\- Selected tariff

\- Subscription status

\- Expiration date



\*\*Receipts\*\*

\- Receipt ID

\- User ID

\- Telegram file ID

\- Selected tariff

\- Processing status

\- Submission timestamp



\## Prediction Data



Prediction files are generated externally and are not included in this repository.



The bot expects the following file:



`output/Future\_Matches\_Predictions.csv`



The prediction generation pipeline is outside the scope of this project.



\## Security



\- Credentials are stored in environment variables.

\- `.env` files are excluded from version control.

\- Database files and generated prediction files are excluded from Git.

\- Administrative operations are restricted by Telegram user ID.



\## Limitations



\- Payment verification is manual.

\- No payment provider integration.

\- Prediction generation is external.

\- FSM state is stored in memory and is reset after restart.

\- The project is intended as a portfolio demonstration and has not been audited for production use.



\## License



For educational and portfolio demonstration purposes.