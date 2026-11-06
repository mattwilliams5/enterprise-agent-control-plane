resource "google_firestore_database" "orders" {
  project     = "storeguard-dr-demo-2026"
  name        = "(default)"
  location_id = "nam7"
  type        = "FIRESTORE_NATIVE"

  # Standard edition for our lightweight DR demonstration.

  # Protect the order ledger from accidental Terraform deletion.
  deletion_policy = "ABANDON"
}
