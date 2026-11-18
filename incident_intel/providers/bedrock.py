"""AWS Bedrock via the model-agnostic Converse API (the original project used invoke_model
with the Anthropic body format). Requires the optional `boto3` package and AWS credentials
from the standard credential chain (profile, env vars or role)."""
from .base import Provider, SYSTEM_PROMPT, build_user_prompt, parse_json_object
from ..errors import (InvalidCredentials, InvalidProviderResponse, ModelUnavailable, ProviderError,
                      ProviderNotConfigured, ProviderUnavailable, RateLimited)


class BedrockProvider(Provider):


    """AWS Bedrock via the Converse API. boto3 is imported lazily so the rest of the app works without it."""
    name = "bedrock"
    label = "AWS Bedrock"

    def is_configured(self):
        return bool(self.model and self.settings.bedrock_region)

    def config_hint(self):
        return "Set BEDROCK_REGION and BEDROCK_MODEL_ID, install boto3 (pip install -r requirements-aws.txt), and configure AWS credentials."

    def _client(self):
        try:
            import boto3
        except ImportError:
            raise ProviderNotConfigured("boto3 is not installed. Run: pip install -r requirements-aws.txt")
        from botocore.config import Config
        return boto3.client("bedrock-runtime", region_name=self.settings.bedrock_region,
                            config=Config(read_timeout=self.settings.request_timeout, retries={"max_attempts": 2}))

    def analyze(self, description, title=None, service=None, reported_severity=None):
        client = self._client()
        try:
            resp = client.converse(
                modelId=self.model,
                system=[{"text": SYSTEM_PROMPT}],
                messages=[{"role": "user", "content": [{"text": build_user_prompt(
                    description, title, service, reported_severity)}]}],
                inferenceConfig={"maxTokens": 2000, "temperature": 0.2})
        except Exception as e:  # botocore exceptions; map by error code without leaking details
            raise self._translate(e)
        try:
            text = "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
        except (KeyError, TypeError):
            raise InvalidProviderResponse("Unexpected response shape from Bedrock.")
        return parse_json_object(text)

    def _translate(self, exc):
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "") if hasattr(exc, "response") else ""
        name = type(exc).__name__
        if code in {"AccessDeniedException", "UnrecognizedClientException", "ExpiredTokenException",
                    "InvalidSignatureException"} or name in {"NoCredentialsError", "PartialCredentialsError"}:
            return InvalidCredentials("AWS credentials are missing, expired or not allowed to invoke this Bedrock model.")
        if code in {"ThrottlingException", "TooManyRequestsException", "ServiceQuotaExceededException"}:
            return RateLimited("Bedrock throttled the request.")
        if code in {"ResourceNotFoundException", "ValidationException", "ModelNotReadyException"}:
            return ModelUnavailable(f"Bedrock rejected model '{self.model}' (check the model ID, region and model access).")
        if code in {"ServiceUnavailableException", "InternalServerException", "ModelTimeoutException"} or \
                name in {"EndpointConnectionError", "ReadTimeoutError", "ConnectTimeoutError"}:
            return ProviderUnavailable("Bedrock is unavailable or timed out.")
        return ProviderError(f"Bedrock request failed ({code or name}).")
