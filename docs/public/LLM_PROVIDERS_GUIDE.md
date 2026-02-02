# LLM Provider Configuration Guide

SentiWiki AI supports **7 major LLM providers** through LiteLLM, giving you flexibility to choose the best model for your needs while keeping complexity manageable.

## Quick Start

1. **Choose your provider** from the [Supported Providers](#supported-providers) list below
2. **Set the API key** in your `.env` file (see [Configuration](#configuration))
3. **Update `config/settings.yaml`** with your provider and model choice
4. **That's it!** The system will automatically use your chosen provider

## Supported Providers

The following 7 providers are supported:

| Provider | Example Models | API Key Env Var | Notes |
|----------|---------------|-----------------|-------|
| **Anthropic** | `claude-3-haiku`, `claude-3-5-sonnet`, `claude-3-opus` | `ANTHROPIC_API_KEY` | Default provider. Supports prompt caching. |
| **OpenAI** | `gpt-4o-mini`, `gpt-4-turbo`, `gpt-3.5-turbo` | `OPENAI_API_KEY` | Most popular, widely used. |
| **Google** | `gemini-pro`, `gemini-ultra`, `gemini-1.5-pro` | `GOOGLE_API_KEY` | Competitive pricing, multimodal. |
| **Groq** | `llama-3-70b`, `mixtral-8x7b`, `gemma-7b` | `GROQ_API_KEY` | Very fast inference, cost-effective. |
| **Cohere** | `command`, `command-r`, `command-r-plus` | `COHERE_API_KEY` | Enterprise-focused, strong reasoning. |
| **Mistral** | `mistral-large`, `mistral-medium`, `mistral-small` | `MISTRAL_API_KEY` | European provider, good performance. |
| **AWS Bedrock** | `bedrock/claude-3`, `bedrock/llama2` | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` | AWS-native, uses AWS credentials. |

## Configuration

### Step 1: Set API Key

Create a `.env` file in the project root (same folder as `pyproject.toml`) and add your provider's API key:

```bash
# For Anthropic (default)
ANTHROPIC_API_KEY=sk-ant-...

# For OpenAI
OPENAI_API_KEY=sk-...

# For Google
GOOGLE_API_KEY=...

# For Groq
GROQ_API_KEY=...

# For Cohere
COHERE_API_KEY=...

# For Mistral
MISTRAL_API_KEY=...

# For AWS Bedrock (requires both)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

**Alternative**: You can export these variables directly in your shell instead of using a `.env` file:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
```

### Step 2: Update Configuration

Edit `config/settings.yaml` to specify your provider and model:

```yaml
llm:
  # Change provider here
  provider: "openai"  # or "google", "cohere", "groq", "mistral", "bedrock"
  model: "gpt-4o-mini"  # or "gemini-pro", "command", etc.
  temperature: 0.1
  max_tokens: 4096
  streaming: true
  prompt_caching: false  # Only supported for Anthropic
```

### Step 3: Provider-Specific Configuration

You can also configure different providers for different parts of the system:

```yaml
llm:
  # Default LLM (used as fallback)
  provider: "anthropic"
  model: "claude-3-haiku-20240307"
  
  # Router LLM (for routing decisions - should be fast/cheap)
  router:
    provider: "groq"  # Fast and cheap
    model: "llama-3-70b"
    temperature: 0.0
  
  # RAG LLM (for technical queries with context - should be capable)
  rag:
    provider: "anthropic"  # More capable
    model: "claude-3-5-sonnet-20241022"
    temperature: 0.1
  
  # Direct LLM (for simple conversational queries - can be fast)
  direct:
    provider: "openai"  # Fast and cheap
    model: "gpt-4o-mini"
    temperature: 0.3
```

## Usage Examples

### Example 1: Switch to OpenAI

**`.env` file:**
```bash
OPENAI_API_KEY=sk-...
```

**`config/settings.yaml`:**
```yaml
llm:
  provider: "openai"
  model: "gpt-4o-mini"
```

### Example 2: Use Google Gemini

**`.env` file:**
```bash
GOOGLE_API_KEY=...
```

**`config/settings.yaml`:**
```yaml
llm:
  provider: "google"
  model: "gemini-pro"
```

### Example 3: Use Groq for Fast Inference

**`.env` file:**
```bash
GROQ_API_KEY=...
```

**`config/settings.yaml`:**
```yaml
llm:
  provider: "groq"
  model: "llama-3-70b"
```

### Example 4: Auto-Detection

The system can auto-detect the provider from the model name for all supported providers:

```yaml
llm:
  # Provider auto-detected from model name
  model: "gpt-4o-mini"  # Detects "openai"
```

Or:

```yaml
llm:
  model: "claude-3-haiku"  # Detects "anthropic"
```

**Auto-detection works for all 7 providers:** Anthropic, OpenAI, Google, Groq, Cohere, Mistral, and AWS Bedrock.

For AWS Bedrock, you can also explicitly specify:

```yaml
llm:
  provider: "bedrock"
  model: "bedrock/claude-3-sonnet"
```

## Provider-Specific Features

### Prompt Caching (Anthropic Only)

Anthropic supports prompt caching, which can reduce latency by up to 80%:

```yaml
llm:
  provider: "anthropic"
  model: "claude-3-haiku-20240307"
  prompt_caching: true  # Only works with Anthropic
```

### AWS Bedrock

AWS Bedrock requires AWS credentials instead of API keys:

**`.env` file:**
```bash
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

**`config/settings.yaml`:**
```yaml
llm:
  provider: "bedrock"
  model: "bedrock/claude-3-sonnet"
```

## Troubleshooting

### Provider Not Working?

1. **Check API Key**: Ensure the correct environment variable is set
2. **Check Provider Name**: Verify the provider name matches exactly (case-sensitive)
3. **Check Model Name**: Some providers require specific model name formats (e.g., `bedrock/claude-3` for AWS Bedrock)
4. **Check Logs**: Look for error messages in the application logs

### Common Issues

**"Provider not found"**
- Ensure the provider name matches exactly (case-sensitive)
- Only the 7 supported providers are available: anthropic, openai, google, groq, cohere, mistral, bedrock

**"API key not found"**
- Verify the environment variable name matches the provider's expected name
- Check that the `.env` file is in the project root
- Ensure the API key is valid and has sufficient credits

**"Model not found"**
- Verify the model name is correct for the provider
- Some providers require a prefix (e.g., `bedrock/claude-3`)
- Check LiteLLM documentation for the correct model name format

## Cost Optimization Tips

Different providers have different pricing models. Here are some tips:

- **Anthropic Claude**: Good balance of cost and quality, supports prompt caching
- **OpenAI GPT-4o-mini**: Very cost-effective for most use cases
- **Groq**: Extremely fast and cheap, great for high-volume applications
- **Google Gemini**: Competitive pricing, good for multimodal tasks
- **Cohere**: Enterprise-focused, good for complex reasoning
- **Mistral**: European provider, competitive pricing
- **AWS Bedrock**: Good for AWS-native deployments, pay-as-you-go

Consider using different providers for different parts of your system:
- **Router**: Use a fast, cheap model (e.g., Groq, GPT-4o-mini)
- **RAG**: Use a capable model (e.g., Claude Sonnet, GPT-4 Turbo)
- **Direct Chat**: Use a fast, cheap model (e.g., Groq, GPT-4o-mini)

## Additional Resources

- [LiteLLM Documentation](https://docs.litellm.ai/) - Full provider details and model names
- [Multi-Provider Support Implementation](troubleshooting/MULTI_PROVIDER_LLM_SUPPORT.md) - Technical details on how multi-provider support works
- [Configuration Reference](../config/settings.yaml) - Full configuration options

## Need Help?

If you're having trouble configuring a provider:

1. Check the [troubleshooting section](#troubleshooting) above
2. Review the [LiteLLM documentation](https://docs.litellm.ai/) for provider-specific requirements
3. Check application logs for detailed error messages
4. Open an issue on GitHub with details about your provider and configuration
