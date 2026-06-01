//! Index CNS contract state from Cube Signet storage + local registration labels.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Serialize, Deserialize, Clone)]
struct ProgramManifest {
    contract_id: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct LabelEntry {
    name: String,
    name_hash: String,
    account: String,
    submitted_at: String,
    confirmed: bool,
}

#[derive(Debug, Serialize, Deserialize)]
struct NameRecord {
    name_hash: String,
    account: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    name: Option<String>,
    source: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct IndexFile {
    updated_at: String,
    contract_id: String,
    records: Vec<NameRecord>,
}

fn main() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let manifest_path = root.join("artifacts/program.json");
    let manifest: ProgramManifest = serde_json::from_slice(
        &fs::read(&manifest_path).unwrap_or_else(|_| {
            eprintln!("Run `cargo run --bin cns-compile` from cube-cns root first.");
            std::process::exit(1);
        }),
    )
    .expect("parse program.json");

    let contract_id = {
        let s = manifest.contract_id.trim();
        let s = s.strip_prefix("0x").unwrap_or(s);
        hex::decode(s).expect("contract_id hex")
    };
    if contract_id.len() != 32 {
        eprintln!("contract_id must be 32 bytes");
        std::process::exit(1);
    }
    let mut contract_arr = [0u8; 32];
    contract_arr.copy_from_slice(&contract_id);

    let storage = std::env::var("CNS_STORAGE_PATH").unwrap_or_else(|_| {
        root.join("../cube/storage/signet/states")
            .to_string_lossy()
            .into_owned()
    });
    let labels_path = root.join("data/labels.json");

    let mut labels: Vec<LabelEntry> = if labels_path.exists() {
        serde_json::from_slice(&fs::read(&labels_path).unwrap()).unwrap_or_default()
    } else {
        Vec::new()
    };

    let label_by_hash: HashMap<String, LabelEntry> = labels
        .iter()
        .map(|e| (e.name_hash.to_lowercase(), e.clone()))
        .collect();

    let db = sled::open(&storage).expect("open states db");
    let tree = db
        .open_tree(contract_arr)
        .unwrap_or_else(|e| {
            eprintln!("Contract tree not found (deploy CNS first?): {e}");
            std::process::exit(1);
        });

    let mut records: Vec<NameRecord> = Vec::new();
    for item in tree.iter().flatten() {
        let name_hash = hex::encode(item.0.as_ref());
        let account = hex::encode(item.1.as_ref());
        let label = label_by_hash.get(&name_hash);
        records.push(NameRecord {
            name_hash: name_hash.clone(),
            account,
            name: label.map(|l| l.name.clone()),
            source: "chain".to_string(),
        });
        if let Some(l) = label {
            if let Some(entry) = labels.iter_mut().find(|e| e.name_hash == l.name_hash) {
                entry.confirmed = true;
            }
        }
    }

    for label in &labels {
        if !records.iter().any(|r| r.name_hash == label.name_hash) {
            records.push(NameRecord {
                name_hash: label.name_hash.clone(),
                account: label.account.clone(),
                name: Some(label.name.clone()),
                source: if label.confirmed {
                    "chain".to_string()
                } else {
                    "pending".to_string()
                },
            });
        }
    }

    records.sort_by(|a, b| a.name_hash.cmp(&b.name_hash));

    let contract_id_str = manifest.contract_id.clone();
    let index = IndexFile {
        updated_at: chrono::Utc::now().to_rfc3339(),
        contract_id: contract_id_str.clone(),
        records,
    };

    let out_dir = root.join("data");
    fs::create_dir_all(&out_dir).ok();
    fs::write(
        out_dir.join("index.json"),
        serde_json::to_string_pretty(&index).expect("json"),
    )
    .expect("write index.json");
    fs::write(
        labels_path,
        serde_json::to_string_pretty(&labels).expect("json labels"),
    )
    .ok();

    println!(
        "Indexed {} records for contract {}",
        index.records.len(),
        contract_id_str
    );
    println!("Wrote {}", out_dir.join("index.json").display());
}
