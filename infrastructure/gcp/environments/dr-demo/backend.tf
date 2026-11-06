terraform {
  backend "gcs" {
    bucket = "storeguard-dr-demo-2026-tfstate"
    prefix = "terraform/dr-demo"
  }
}
