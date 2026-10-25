from __future__ import annotations

import asyncio
import os
import time

import httpx


API_ROOT = "https://api-sandbox.stitchcredit.com/api"

# Exact, published fake CalHacks sandbox bodies. Never accept a person's fields
# from the browser here: requests must match the free canned test cases exactly.
PERSONA_REQUESTS = {
    "P01": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "MARGARET", "lastName": "OKAFOR", "ssn": "666701001", "addresses": [{"addressLine1": "1420 WILLOW CREEK DR", "city": "SAN JOSE", "state": "CA", "postalCode": "95125", "borrowerResidencyType": "Current"}]},
    },
    "P02": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "DANIEL", "lastName": "WHITFIELD", "ssn": "666701002", "addresses": [{"addressLine1": "88 LAKESHORE BLVD", "city": "AUSTIN", "state": "TX", "postalCode": "78746", "borrowerResidencyType": "Current"}]},
    },
    "P03": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "JASMINE", "lastName": "REYES", "ssn": "666701003", "addresses": [{"addressLine1": "2210 UNIVERSITY AVE APT 4B", "city": "BERKELEY", "state": "CA", "postalCode": "94704", "borrowerResidencyType": "Current"}]},
    },
    "P04": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "TOMAS", "lastName": "LINDQVIST", "ssn": "666701004", "addresses": [{"addressLine1": "415 PINE ST UNIT 12", "city": "SEATTLE", "state": "WA", "postalCode": "98101", "borrowerResidencyType": "Current"}]},
    },
    "P05": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "RICKY", "lastName": "DALTON", "ssn": "666701005", "addresses": [{"addressLine1": "7031 SUNSET RIDGE RD", "city": "ORLANDO", "state": "FL", "postalCode": "32819", "borrowerResidencyType": "Current"}]},
    },
    "P06": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "ANGELA", "lastName": "MORRISSEY", "ssn": "666701006", "addresses": [{"addressLine1": "960 MAPLEWOOD AVE", "city": "COLUMBUS", "state": "OH", "postalCode": "43209", "borrowerResidencyType": "Current"}]},
    },
    "P07": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "MARCUS", "lastName": "BELLAMY", "ssn": "666701007", "addresses": [{"addressLine1": "1507 PEACHTREE INDUSTRIAL BLVD", "city": "ATLANTA", "state": "GA", "postalCode": "30341", "borrowerResidencyType": "Current"}]},
    },
    "P08": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "PRIYA", "lastName": "VENKATESAN", "ssn": "666701008", "addresses": [{"addressLine1": "3300 N LAKE SHORE DR APT 15C", "city": "CHICAGO", "state": "IL", "postalCode": "60657", "borrowerResidencyType": "Current"}]},
    },
    "P09": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "DEREK", "lastName": "HOLLOWAY", "ssn": "666701009", "addresses": [{"addressLine1": "4875 W COLFAX AVE", "city": "DENVER", "state": "CO", "postalCode": "80204", "borrowerResidencyType": "Current"}]},
    },
    "P10": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "LAUREN", "lastName": "KOWALCZYK", "ssn": "666701010", "addresses": [{"addressLine1": "1181 WOODWARD AVE", "city": "DETROIT", "state": "MI", "postalCode": "48226", "borrowerResidencyType": "Current"}]},
    },
    "P11": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "BRANDON", "lastName": "SZABO", "ssn": "666701011", "addresses": [{"addressLine1": "2640 HIGHLAND AVE APT 7", "city": "NATIONAL CITY", "state": "CA", "postalCode": "91950", "borrowerResidencyType": "Current"}]},
    },
    "P12": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "VICTOR", "lastName": "ANAND", "ssn": "666701012", "addresses": [{"addressLine1": "55 WATER ST FL 20", "city": "NEW YORK", "state": "NY", "postalCode": "10041", "borrowerResidencyType": "Current"}]},
    },
    "P13": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "KAYLA", "lastName": "BRENNAN", "ssn": "666701013", "addresses": [{"addressLine1": "9021 KINGSTON PIKE", "city": "KNOXVILLE", "state": "TN", "postalCode": "37923", "borrowerResidencyType": "Current"}]},
    },
    "P15": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "NICOLE", "lastName": "FARRAGUT", "ssn": "666701015", "addresses": [{"addressLine1": "7700 NE 72ND AVE", "city": "PORTLAND", "state": "OR", "postalCode": "97218", "borrowerResidencyType": "Current"}]},
    },
    "P16": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "SAMUEL", "lastName": "OYELARAN", "ssn": "666701016", "addresses": [{"addressLine1": "1200 BRICKELL BAY DR APT 2203", "city": "MIAMI", "state": "FL", "postalCode": "33131", "borrowerResidencyType": "Current"}]},
    },
    "P17": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "ELENA", "lastName": "CASTELLANOS", "ssn": "666701017", "addresses": [{"addressLine1": "4400 N CENTRAL EXPY STE 100", "city": "DALLAS", "state": "TX", "postalCode": "75206", "borrowerResidencyType": "Current"}]},
    },
    "P18": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "TERRENCE", "lastName": "ABERNATHY", "ssn": "666701018", "addresses": [{"addressLine1": "2102 S HALSTED ST", "city": "CHICAGO", "state": "IL", "postalCode": "60608", "borrowerResidencyType": "Current"}]},
    },
    "P19": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "GRACE", "lastName": "NAKAMURA", "ssn": "666701019", "addresses": [{"addressLine1": "1850 SOLANO AVE", "city": "BERKELEY", "state": "CA", "postalCode": "94707", "borrowerResidencyType": "Current"}]},
    },
    "P20": {
        "config": "tu-prequal-fico9",
        "body": {"firstName": "DOLORES", "lastName": "WHITCOMB", "ssn": "666701020", "addresses": [{"addressLine1": "612 OCEAN VIEW DR", "city": "SANTA BARBARA", "state": "CA", "postalCode": "93109", "borrowerResidencyType": "Current"}]},
    },
}


class CRSNotConfigured(Exception):
    pass


class CRSRequestError(Exception):
    pass


class CRSSandboxClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def _login(self) -> str:
        username = os.getenv("CRS_USERNAME")
        password = os.getenv("CRS_PASSWORD")
        if not username or not password:
            raise CRSNotConfigured("Set CRS_USERNAME and CRS_PASSWORD in the backend environment to enable CRS sandbox pulls.")
        async with self._lock:
            if self._token and time.time() < self._expires_at:
                return self._token
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=2.0)) as client:
                try:
                    response = await client.post(f"{API_ROOT}/users/login", json={"username": username, "password": password})
                except httpx.HTTPError as exc:
                    raise CRSRequestError("Could not reach the CRS sandbox login service.") from exc
            if response.status_code != 200:
                # No automatic retries: the CRS sandbox can disable an account
                # after repeated failed logins.
                raise CRSRequestError(f"CRS sandbox login failed with HTTP {response.status_code}; check credentials once before retrying.")
            data = response.json()
            token = data.get("token")
            if not token:
                raise CRSRequestError("CRS sandbox login succeeded without returning a token.")
            self._token = token
            self._expires_at = time.time() + 20 * 60
            return token

    async def pull_persona(self, persona_id: str) -> dict:
        request = PERSONA_REQUESTS.get(persona_id)
        if not request:
            raise CRSRequestError("This persona is not a playable CRS sandbox credit-report case in this demo.")
        token = await self._login()
        endpoint = f"{API_ROOT}/transunion/credit-report/standard/{request['config']}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=3.0)) as client:
            try:
                response = await client.post(endpoint, headers={"Authorization": f"Bearer {token}"}, json=request["body"])
            except httpx.HTTPError as exc:
                raise CRSRequestError("Could not reach the CRS sandbox credit-report endpoint.") from exc
        if response.status_code == 401:
            self._token = None
            self._expires_at = 0
            raise CRSRequestError("The CRS token was rejected. The next manual pull can log in once again; no automatic retry was made.")
        if response.status_code != 200:
            raise CRSRequestError(f"CRS sandbox returned HTTP {response.status_code}.")
        data = response.json()
        errors = data.get("errorMessages") or []
        if errors:
            message = "; ".join(str(item.get("creditErrorMessageText", "CRS report returned an error")) for item in errors[:3])
            raise CRSRequestError(message)
        scores = data.get("scores") or []
        score_entry = next((item for item in scores if isinstance(item.get("scoreValue"), (int, float))), None)
        credit_files = data.get("creditFiles") or []
        file_status = next((item.get("creditFileDetail") for item in credit_files if item.get("creditFileDetail")), "Unknown")
        return {
            "persona_id": persona_id,
            "score": score_entry.get("scoreValue") if score_entry else None,
            "model": score_entry.get("modelName") if score_entry else None,
            "file_status": file_status,
            "request_id": response.headers.get("RequestID"),
            "source": "CRS sandbox synthetic persona",
        }
