"""Thin GenLayer client for the CourtPay case court."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from genlayer_py import create_account, create_client, studionet

STATE_DIR = os.environ.get("COURTPAY_STATE_DIR", os.path.join(os.getcwd(), ".courtpay"))


def _state_path() -> str:
    os.makedirs(STATE_DIR, exist_ok=True)
    return os.path.join(STATE_DIR, "state.json")


def load_state() -> Dict[str, Any]:
    path = _state_path()
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_state(state: Dict[str, Any]) -> None:
    with open(_state_path(), "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


class Court:
    def __init__(self, private_key: str, chain=studionet, contract: Optional[str] = None):
        self.account = create_account(private_key)
        self.client = create_client(chain=chain, account=self.account)
        self.contract = contract or load_state().get("contract")

    # ------------------------------------------------------------------ setup

    def deploy(self, code_path: str) -> str:
        with open(code_path, "rb") as handle:
            code = handle.read()
        tx = self.client.deploy_contract(code=code, args=[])
        receipt = self._wait(tx)
        address = (receipt.get("data") or {}).get("contract_address")
        if not address:
            raise RuntimeError("deployment returned no contract address: %s" % receipt)
        self.contract = address
        state = load_state()
        state.update({"contract": address, "deploy_tx": tx, "deployer": self.account.address})
        save_state(state)
        return address

    def _wait(self, tx: str, timeout: int = 600) -> Dict[str, Any]:
        deadline = time.time() + timeout
        receipt = self.client.wait_for_transaction_receipt(tx)
        status = receipt.get("status")
        if status not in (5, 6) and receipt.get("statusName") not in ("ACCEPTED", "FINALIZED"):
            raise RuntimeError("transaction failed: %s" % json.dumps(receipt, default=str)[:800])
        for entry in (receipt.get("consensus_data") or {}).get("leader_receipt") or []:
            if str(entry.get("execution_result", "")).upper() == "ERROR":
                raise RuntimeError(
                    "contract execution error in %s: %s"
                    % (tx, json.dumps(entry.get("genvm_result", {}), default=str)[:600])
                )
        return receipt

    def _write(self, function_name: str, args: list) -> str:
        if not self.contract:
            raise RuntimeError("no contract address; run deploy first")
        tx = self.client.write_contract(address=self.contract, function_name=function_name, args=args)
        self._wait(tx)
        return tx

    def _read(self, function_name: str, args: Optional[list] = None) -> Any:
        if not self.contract:
            raise RuntimeError("no contract address; run deploy first")
        return self.client.read_contract(address=self.contract, function_name=function_name, args=args or [])

    # ------------------------------------------------------------------ court

    def stats(self) -> Dict[str, Any]:
        return self._read("get_stats")

    def open_case(self, seller: str, resource_url: str, promise: str, price_units: int, asset: str, receipt_hash: str) -> Dict[str, Any]:
        before = int(self.stats().get("cases", 0))
        tx = self._write(
            "open_case",
            [seller, resource_url, promise, int(price_units), asset, receipt_hash],
        )
        case_id = "case-" + str(before + 1)
        return {"case_id": case_id, "tx": tx}

    def dispute(self, case_id: str, deliverable_url: str, complaint: str) -> str:
        return self._write("dispute", [case_id, deliverable_url, complaint])

    def judge(self, case_id: str) -> str:
        return self._write("judge", [case_id])

    def appeal(self, case_id: str) -> str:
        return self._write("appeal", [case_id])

    def get_case(self, case_id: str) -> Dict[str, Any]:
        return self._read("get_case", [case_id])

    def refund_amount(self, case_id: str) -> int:
        return int(self._read("refund_amount", [case_id]))
