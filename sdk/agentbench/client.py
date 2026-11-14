from __future__ import annotations

import httpx

class AgentBenchError(Exception):
    def __init__(self, status: int, detail):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail

class AgentBench:
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: str | None = None, timeout: float = 10.0):
        
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        
        self._http = httpx.Client(base_url=base_url, headers=headers, timeout=timeout)

    
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "AgentBench":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    
    def _request(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None):
        try:
            resp = self._http.request(method, path, params=params, json=json)
        except httpx.HTTPError as exc:  
            raise AgentBenchError(0, f"could not reach server: {exc}") from exc

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:  
                body = None
            
            detail = body["detail"] if isinstance(body, dict) and "detail" in body else resp.text
            raise AgentBenchError(resp.status_code, detail)

        return resp.json()

    def create_project(self, name: str) -> dict:
        return self._request("POST", "/v1/projects", json={"name": name})

    def list_projects(self, name: str | None = None) -> list[dict]:
        params = {"name": name} if name is not None else None
        return self._request("GET", "/v1/projects", params=params)

    def get_or_create_project(self, name: str) -> dict:
        for p in self.list_projects(name=name):
            if p["name"] == name:
                return p
        try:
            return self.create_project(name)
        except AgentBenchError as e:
            if e.status != 409:
                raise
            return next(p for p in self.list_projects(name=name) if p["name"] == name)

    def create_experiment(self, project_id , name: str, config: dict | None = None) -> dict:
        return self._request(
            "POST",
            f"/v1/projects/{project_id}/experiments",
            json={"name": name, "config": config or {}},
        )

    def list_experiments(self, project_id: str) -> list[dict]:
        return self._request("GET", f"/v1/projects/{project_id}/experiments")
    
    def ingest(self, traces: list[dict]) -> dict:
        return self._request("POST", "/v1/ingest", json={"traces": traces})

    def list_traces(self,project_id: int | None = None,status: str | None = None,limit: int = 100,offset: int = 0,) -> list[dict]:
        params = {"limit": limit, "offset": offset}
        if project_id is not None:
            params["project_id"] = project_id
        if status is not None:
            params["status"] = status
        return self._request("GET", "/v1/traces", params=params)

    def get_trace(self, trace_id: str) -> dict:
        return self._request("GET", f"/v1/traces/{trace_id}")
    
    def create_new_dataset(self,name:str,version:str,records:list[dict]) -> dict:
        return self._request("POST", "/v1/dataset", json={"name": name,"version":version,"records":records})
    
    def get_dataset(self,name:str,version: str|None=None) -> dict:
        params={"name":name,"version":version or "latest"}
        return self._request("GET",f"/v1/dataset/name/{name}",params=params)