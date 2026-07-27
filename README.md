# QB-SAO — Sistema Administracion de Ordenes

Open-OMS is a modern, high-performance order status monitoring and management system. It serves as an independent module designed to track orders, manage statuses, and sync data in real-time between local systems and SAP Business One (HANA).

## Features

- **Real-Time Order Monitoring**: Real-time dashboard with status counters (KPIs) and instant filtering/search.
- **SAP Business One Integration**: Connects with SAP HANA to sync order metadata, invoices, and delivery status automatically.
- **Server-Sent Events (SSE)**: Auto-refreshes data and plays desktop notifications for status transitions.
- **Excel Exports**: Seamlessly download filtered lists into Excel format.
- **Multi-Role Security**: Built-in authentication with granular user roles (Admin, Manager, Operator, Seller).
- **Background Sync Workers**: Automated recovery mechanism for SAP synchronization.
- **Detailed System Health Dashboard**: Continuous monitoring of SAP connection, database state, and background thread status.

## Technologies Used

- **Backend**: Python (Flask, SQLAlchemy, Pandas, PyODBC, hdbcli)
- **Frontend**: Alpine.js, Tailwind CSS, Outfit Google Font, HTML5, Vanilla CSS
- **Metrics**: Prometheus Flask Exporter
- **Database**: SAP HANA & SQL Database engines

## Setup & Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/Charly-bite/open-oms.git
   cd open-oms
   ```

2. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill in the required credentials:
   ```bash
   cp .env.example .env
   ```
   Specify your SAP HANA hosts, database connections, and Flask secret keys.

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Application**:
   Execute the startup batch script on Windows:
   ```cmd
   run.bat
   ```
   Or run the Flask app directly:
   ```bash
   python app.py
   ```
   The application will be hosted locally at `http://localhost:5003`.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to submit pull requests and our contribution guidelines. Adhere to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) in all community interactions.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.


---
*Graph Context: Return to [[Home]] (Architecture)*
