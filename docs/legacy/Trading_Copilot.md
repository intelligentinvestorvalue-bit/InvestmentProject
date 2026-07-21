# Trading Co-Pilot

Trading Co-Pilot is a web application designed for financial data analysis. It provides tools to view insider trading data, analyze company financials, and explore sector and industry trends.

## Project Structure

The project is divided into two main parts:

-   `trading-copilot-backend/`: A Flask-based backend that serves financial data and handles data scraping.
-   `trading-copilot-frontend/`: A React-based frontend for data visualization and user interaction.

---

## Backend Setup (`trading-copilot-backend/`)

The backend is a Python Flask application.

### Prerequisites

-   Python 3.x

### Setup Steps

1.  **Create and activate a virtual environment:**

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```

2.  **Install dependencies:**

    Navigate to the `trading-copilot-backend` directory and install the required packages:

    ```bash
    pip install -r requirements.txt
    ```

3.  **Database Initialization:**

    The application uses an SQLite database (`financials.db`) to store scraped financial data. The database is automatically initialized when you run the application for the first time.

4.  **Run the backend server:**

    From the `trading-copilot-backend` directory, run the Flask application:

    ```bash
    python app.py
    ```

    The backend server will start on `http://127.0.0.1:5000`.

---

## Frontend Setup (`trading-copilot-frontend/`)

The frontend is a React application.

### Prerequisites

-   Node.js and npm (or yarn)

### Setup Steps

1.  **Install dependencies:**

    Navigate to the `trading-copilot-frontend` directory and install the required npm packages:

    ```bash
    npm install
    ```

2.  **Run the frontend development server:**

    ```bash
    npm start
    ```

    The frontend development server will start, and the application will open in your default web browser at `http://localhost:3000`.

---

## Data Sources

-   **Insider Trading Data:** The application uses the `CF-Insider-Trading-equities.csv` file located in `trading-copilot-backend/app/`.
-   **Company Financials:** Financial data is scraped from [Screener.in](https://www.screener.in/) when a user requests data for a specific company symbol. The scraped data is cached in the `financials.db` SQLite database.

---

## API Endpoints

The Flask backend provides the following API endpoints:

-   `GET /api/data`: Returns all insider trading data from the CSV file.
-   `GET /api/financials/<symbol>`: Fetches and returns financial data for a given company symbol.
-   `GET /api/sectors`: Returns a list of distinct sectors from the database.
-   `GET /api/industries`: Returns a list of distinct industries for a given sector.
-   `GET /api/filtered-data`: Returns filtered financial data based on sector and industry.

---

## How to Run the Entire Application

1.  **Start the backend server:**
    -   Open a terminal, navigate to `trading-copilot-backend/`, and run `python app.py`.

2.  **Start the frontend server:**
    -   Open another terminal, navigate to `trading-copilot-frontend/`, and run `npm start`.

3.  **Access the application:**
    -   Open your web browser and go to `http://localhost:3000`.
