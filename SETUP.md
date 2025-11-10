# SSW.FatDigester - Quick Setup

## 🚀 One-Command Deployment

### Prerequisites
- Azure CLI installed ([Install here](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli))
- Azure subscription with OpenAI access
- GitHub repository

### Step 1: Run Setup Script (2 minutes)

```bash
./setup-azure.sh
```

**What it does:**
- ✅ Creates Azure Key Vault
- ✅ Stores your OpenAI credentials securely
- ✅ Creates GitHub Actions service principal
- ✅ Outputs GitHub secret JSON

### Step 2: Add GitHub Secret (1 minute)

1. Copy the JSON output from the script
2. Go to: **GitHub Repo** → **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `AZURE_CREDENTIALS`
5. Value: Paste the JSON
6. Click **Add secret**

### Step 3: Deploy (2 minutes)

```bash
git add .
git commit -m "Deploy to Azure"
git push origin main
```

**Done!** Your app will be live at:
```
https://ssw-fatdigester-prod.azurewebsites.net
```

---

## 🎯 That's It!

You only need **ONE GitHub secret** (`AZURE_CREDENTIALS`).

All Azure OpenAI credentials are securely stored in Azure Key Vault, not in GitHub.

---

## 🔄 Updates

To deploy updates, just push to main:
```bash
git push origin main
```

GitHub Actions automatically:
- Updates infrastructure (if changed)
- Deploys new code
- Restarts the app

---

## 📊 Monitoring

### Check App Status
```bash
curl https://ssw-fatdigester-prod.azurewebsites.net/health
```

### View Logs
```bash
az webapp log tail \
  --name ssw-fatdigester-prod \
  --resource-group ssw-fatdigester-rg
```

### Check Stats
```bash
curl https://ssw-fatdigester-prod.azurewebsites.net/stats
```

---

## 🔧 Update OpenAI Credentials

If you need to rotate API keys:

```bash
az keyvault secret set \
  --vault-name ssw-fatdigester-kv \
  --name "AZURE-OPENAI-API-KEY" \
  --value "new-key-here"

# Restart app to pick up new value
az webapp restart \
  --name ssw-fatdigester-prod \
  --resource-group ssw-fatdigester-rg
```

---

## 💰 Cost

- **App Service B1**: $13/month
- **Key Vault**: $0.03/month (first 10,000 operations free)
- **Azure OpenAI**: Pay-per-use

**Total: ~$15-20/month** (depending on AI usage)

---

## 🗑️ Cleanup

To delete everything:

```bash
az group delete --name ssw-fatdigester-rg --yes
```

---

## 🆘 Need Help?

### Common Issues

**"Setup script failed"**
- Make sure Azure CLI is installed: `az --version`
- Login to Azure: `az login`
- Check you have permissions to create resources

**"GitHub Actions failing"**
- Verify `AZURE_CREDENTIALS` secret is set
- Check the Actions tab for error messages
- Ensure service principal has Contributor role

**"App not starting"**
- Check logs: `az webapp log tail --name ssw-fatdigester-prod --resource-group ssw-fatdigester-rg`
- Verify OpenAI credentials in Key Vault
- Ensure deployment name matches your Azure OpenAI resource

### Get More Help

See detailed documentation:
- `GITHUB_SECRETS.md` - Secret configuration details
- `AZURE_SETUP.md` - Advanced setup options
- `DEPLOYMENT.md` - Troubleshooting and scaling

---

## ✨ Features

Your deployed app includes:
- 🔒 Secure credential storage (Key Vault)
- 📊 Monitoring (Application Insights)
- 🔄 Auto cleanup (memory management)
- 🚀 CI/CD (GitHub Actions)
- 🛡️ HTTPS enforced
- ⚡ Fast deployment (~5 minutes)

---

**Made with ❤️ by SSW**

