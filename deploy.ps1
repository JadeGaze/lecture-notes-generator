Write-Host "=== Deply started ===" -ForegroundColor Green

$TerraformVars = Get-Content "terraform/terraform.tfvars" -Raw
$CLOUD_ID = ($TerraformVars | Select-String 'cloud_id\s*=\s*"([^"]+)"').Matches.Groups[1].Value
$FOLDER_ID = ($TerraformVars | Select-String 'folder_id\s*=\s*"([^"]+)"').Matches.Groups[1].Value
$PREFIX = ($TerraformVars | Select-String 'prefix\s*=\s*"([^"]+)"').Matches.Groups[1].Value

Write-Host "1. Terraform init..." -ForegroundColor Yellow
Set-Location terraform
terraform init

Write-Host "2. Terraform apply..." -ForegroundColor Yellow
terraform apply -auto-approve

Write-Host "3. Get ID Container Registry..." -ForegroundColor Yellow
$REGISTRY_ID = terraform output -raw registry_id
Write-Host "Registry ID: $REGISTRY_ID" -ForegroundColor Cyan

Write-Host "4. Auth Container Registry..." -ForegroundColor Yellow
yc container registry configure-docker

Write-Host "5. docker web build..." -ForegroundColor Yellow
Set-Location ..
docker build -f "D:\ITIS\clouds\genertor\docker\web.Dockerfile" -t "cr.yandex/$REGISTRY_ID/web:latest" .

Write-Host "6. docker worker build..." -ForegroundColor Yellow
docker build -f "D:\ITIS\clouds\genertor\docker\worker.Dockerfile" -t "cr.yandex/$REGISTRY_ID/worker:latest" .

Write-Host "7. push into registry..." -ForegroundColor Yellow
docker push "cr.yandex/$REGISTRY_ID/web:latest"
docker push "cr.yandex/$REGISTRY_ID/worker:latest"

Write-Host "9. update structure..." -ForegroundColor Yellow
Set-Location terraform
terraform taint yandex_serverless_container.web
terraform taint yandex_serverless_container.worker
terraform apply -auto-approve

Write-Host "=== Deploy finished! ===" -ForegroundColor Green
Write-Host ""
$API_URL = terraform output -raw api_gateway_url
Write-Host "API Gateway URL: $API_URL" -ForegroundColor Cyan
Write-Host "YDB Endpoint: $YDB_ENDPOINT" -ForegroundColor Cyan
Write-Host "YDB Database: $YDB_DATABASE" -ForegroundColor Cyan
