Repository structure overview
graph TD A[ominimo-api-gateway] --> B[endpoints] A --> C[gateway] A --> D[tests] A --> E[docs]

B --> B1[model_a_endpoint] B --> B2[model_b_endpoint] B --> B3[model_c_endpoint]

C --> C1[app] C --> C2[config] C --> C3[logs]

C1 --> C11[main.py] C1 --> C12[routing.py] C1 --> C13[observability.py] C1 --> C14[models.py] C1 --> C15[config.py]

C2 --> C21[models.yaml]

D --> D1[test_gateway.py] D --> D2[test_sample_payloads.py] D --> D3[demo_suite.py]

E --> E1[architecture.md] E --> E2[adding-new-model.md] E --> E3[testing-routing.md] E --> E4[observability.md]

System architecture
Client[Client Application / Tester] -->|POST /price| Gateway[API Gateway (FastAPI)]

subgraph Docker_Network["Docker Network: pricing-network"]
    Gateway -->|/predict| ModelA[Model A API]
    Gateway -->|/predict| ModelB[Model B API]
    Gateway -->|/predict| ModelC[Model C API]
end

Gateway -->|GET /metrics| Prometheus[(Prometheus / Grafana)]
Gateway -->|Logs| LogFiles[(gateway.log, routing.log, metrics.log)]
Gateway -->|Reload Config| ConfigFile[models.yaml]

style Gateway fill:#aaf,stroke:#333,stroke-width:2px
style ModelA fill:#afa,stroke:#333,stroke-width:1px
style ModelB fill:#afa,stroke:#333,stroke-width:1px
style ModelC fill:#afa,stroke:#333,stroke-width:1px
Request lifecycle (sequence diagram)
sequenceDiagram participant U as User / Test Client participant G as API Gateway participant R as RouterEngine participant M as Model Service (A/B/C)

U->>G: POST /price {payload}
G->>R: route_request(payload)
R-->>G: selected model_id (e.g., "model-b")
G->>M: POST /predict
M-->>G: {model_name, price, breakdown}
G-->>U: 200 OK + gateway_metadata
Internal gateway component interaction
graph TD A[main.py] --> B[routing.py] A --> C[observability.py] A --> D[config.py] A --> E[models.py] B -->|reads| F[models.yaml] C -->|writes| G[logs/*.log] C -->|exposes| H[/metrics]
