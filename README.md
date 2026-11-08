
## Architecture

The application consists of three main components: Telegram interface, business logic, and persistent storage.

### Application Workflow

```mermaid
flowchart TD
    subgraph USER["Telegram User"]
        A["Select Subscription Plan"]
        B["Submit Payment Receipt"]
        H["Request Predictions"]
    end

    subgraph ADMIN["Administrator"]
        C["Review Payment Receipt"]
        D{"Payment Decision"}
    end

    subgraph APP["Bot Application"]
        E["Process Receipt Decision"]
        I["Validate User Access"]
        J{"Access Type"}
        K["Consume 1 Credit"]
        L["Allow Unlimited Download"]
        M["Deliver Prediction File"]
        N["Refund Credit if Delivery Fails"]
    end

    subgraph DATA["SQLite Database"]
        F[("Users & Receipts")]
        G[("Access Information")]
    end

    A --> B
    B --> C
    C --> D
    D -->|Approved| E
    D -->|Rejected| F
    E --> F
    F --> G

    H --> I
    I --> J
    J -->|Available Credits| K
    J -->|Active Unlimited| L
    J -->|No Access| O["Access Denied"]

    K --> M
    L --> M
    M -->|Delivery Failed| N
    N --> G
    M -->|Delivery Successful| P["File Delivered"]
```

### Payment Processing

Receipt approval and access activation are handled within a single database transaction.

```mermaid
flowchart TD
    A["Administrator Approves Receipt"] --> B["process_receipt_decision()"]
    B --> C["BEGIN IMMEDIATE"]
    C --> D{"Already Processed?"}

    D -->|Yes| E["Stop Processing"]
    D -->|No| F["Update Receipt Status"]

    F --> G{"Selected Tariff"}
    G -->|5 Predictions| H["Add 5 Credits"]
    G -->|15 Predictions| I["Add 15 Credits"]
    G -->|Monthly Unlimited| J["Activate 30-Day Access"]

    H --> K["COMMIT"]
    I --> K
    J --> K

    K --> L["Notify User"]

    F -.->|Database Error| M["ROLLBACK"]
    M --> N["Preserve Previous State"]
```

The transaction ensures that receipt status and access allocation remain consistent. A receipt cannot grant access more than once.
