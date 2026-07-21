# Trading Experiment Project

This project is a Flask-based backend that provides API endpoints to retrieve financial data and insider trading information for a given stock ticker. It uses the `sec-api.io` service to fetch the data and stores it in a local SQLite database to avoid repeated API calls.

## Project Structure

The project is organized into the following files:

- `app.py`: The main Flask application file. It defines the API endpoints and handles the logic for fetching and storing data.
- `sec_api.py`: This file contains the functions that interact with the `sec-api.io` API.
- `db.py`: This file sets up the database connection using SQLAlchemy.
- `models.py`: This file defines the database models for the `Financial` and `InsiderTrade` tables.
- `requirements.txt`: This file lists the Python dependencies required for the project.
- `.env`: This file stores the `SEC_API_KEY`.

## How to Replicate the Project

To replicate this project from scratch, follow these steps:

### 1. Set up the Project Directory

Create a directory for your project and inside it, create a `sec_backend` directory.

```bash
mkdir Trading_Experiment
cd Trading_Experiment
mkdir sec_backend
cd sec_backend
```

### 2. Create the Python Files

Create the following Python files inside the `sec_backend` directory with the content described in the previous sections:

- `app.py`
- `sec_api.py`
- `db.py`
- `models.py`

### 3. Create the `requirements.txt` File

Create a `requirements.txt` file with the following content:

```
flask
requests
python-dotenv
sqlalchemy
```

### 4. Create the `.env` File

Create a `.env` file and add your `sec-api.io` API key:

```
SEC_API_KEY=your_sec_api_key
```

### 5. Install Dependencies

Install the required Python packages using pip:

```bash
pip install -r requirements.txt
```

### 6. Run the Application

Run the Flask application:

```bash
python app.py
```

The application will start a development server on `http://127.0.0.1:5001`.

### 7. Use the API Endpoints

You can now access the following API endpoints:

- `http://127.0.0.1:5001/api/financials/<ticker>`: Get financial data for a given ticker.
- `http://127.0.0.1:5001/api/insider-trading/<ticker>`: Get insider trading information for a given ticker.

Replace `<ticker>` with the stock ticker you want to query (e.g., `AAPL` for Apple).
