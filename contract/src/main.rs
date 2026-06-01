//! Compile the CNS (Cube Name Service) program to hex for `deploy`.

use cube::constructive::calldata::element_type::CalldataElementType;
use cube::executive::executable::compiler::compiler::ProgramCompiler;
use cube::executive::executable::executable::Program;
use cube::executive::executable::method::compiler::compiler::MethodCompiler;
use cube::executive::executable::method::method_type::MethodType;
use cube::executive::executable::method::program_method::ProgramMethod;
use cube::executive::opcode::opcode::Opcode;
use cube::executive::opcode::opcodes::altstack::{op_fromaltstack::OP_FROMALTSTACK, op_toaltstack::OP_TOALTSTACK};
use cube::executive::opcode::opcodes::coin::{
    op_ext_balance::OP_EXT_BALANCE, op_self_balance::OP_SELF_BALANCE, op_transfer::OP_TRANSFER,
};
use cube::executive::opcode::opcodes::flow::{op_fail::OP_FAIL, op_nop::OP_NOP, op_returnall::OP_RETURNALL};
use cube::executive::opcode::opcodes::push::op_true::OP_TRUE;
use cube::executive::opcode::opcodes::stack::op_swap::OP_SWAP;
use cube::executive::opcode::opcodes::storage::{op_sread::OP_SREAD, op_swrite::OP_SWRITE};
use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

fn fix_opcode_byte(b: &mut u8) {
    match *b {
        0xc8 => *b = 0xcd, // SWRITE
        0xc9 => *b = 0xce, // SREAD
        0xc0 => *b = 0xca, // EXT_BALANCE
        0xc1 => *b = 0xcb, // SELF_BALANCE
        0xc2 => *b = 0xcc, // TRANSFER
        _ => {}
    }
}

/// Patch opcode scripts only (do not rewrite calldata type bytes like 0x05 Account).
fn fix_opcode_bytes_in_methods(bytes: &mut [u8]) {
    let mut i = 0usize;
    let name_len = bytes[i] as usize;
    i += 1 + name_len;
    i += 1;
    if bytes[i - 1] == 1 {
        let meta_len = u16::from_le_bytes([bytes[i], bytes[i + 1]]) as usize;
        i += 2 + meta_len;
    }
    let method_count = bytes[i] as usize;
    i += 1;
    for _ in 0..method_count {
        let mlen = bytes[i] as usize;
        i += 1 + mlen + 1; // name + method type
        let nargs = bytes[i] as usize;
        i += 1;
        for _ in 0..nargs {
            i += 1;
            if bytes[i - 1] == 0x07 {
                i += 1;
            }
        }
        let opc = u16::from_le_bytes([bytes[i], bytes[i + 1]]) as usize;
        i += 2;
        for b in &mut bytes[i..i + opc] {
            fix_opcode_byte(b);
        }
        i += opc;
    }
}

fn main() {
    // register(name_hash, account) — stack: hash, account(top) → SWAP → SWRITE
    let register = ProgramMethod::new(
        "register".to_string(),
        MethodType::Callable,
        vec![CalldataElementType::Bytes(31), CalldataElementType::Account],
        vec![
            Opcode::OP_SWAP(OP_SWAP),
            Opcode::OP_SWRITE(OP_SWRITE),
            Opcode::OP_NOP(OP_NOP),
            Opcode::OP_RETURNALL(OP_RETURNALL),
        ],
    )
    .expect("register");

    // resolve(name_hash) → account or false
    let resolve = ProgramMethod::new(
        "resolve".to_string(),
        MethodType::Callable,
        vec![CalldataElementType::Bytes(31)],
        vec![
            Opcode::OP_SREAD(OP_SREAD),
            Opcode::OP_NOP(OP_NOP),
            Opcode::OP_NOP(OP_NOP),
            Opcode::OP_RETURNALL(OP_RETURNALL),
        ],
    )
    .expect("resolve");

    // renew(name_hash, account) — same as register (update owner)
    let renew = ProgramMethod::new(
        "renew".to_string(),
        MethodType::Callable,
        vec![CalldataElementType::Bytes(31), CalldataElementType::Account],
        vec![
            Opcode::OP_SWAP(OP_SWAP),
            Opcode::OP_SWRITE(OP_SWRITE),
            Opcode::OP_NOP(OP_NOP),
            Opcode::OP_RETURNALL(OP_RETURNALL),
        ],
    )
    .expect("renew");

    // xfer(name_hash, amount_u32) — contract pays resolved account
    // Calldata: hash bottom, amount top → SWAP → alt amount → SREAD → xfer
    let xfer = ProgramMethod::new(
        "xfer".to_string(),
        MethodType::Callable,
        vec![CalldataElementType::Bytes(31), CalldataElementType::U32],
        vec![
            Opcode::OP_SWAP(OP_SWAP),
            Opcode::OP_TOALTSTACK(OP_TOALTSTACK),
            Opcode::OP_SREAD(OP_SREAD),
            Opcode::OP_FROMALTSTACK(OP_FROMALTSTACK),
            Opcode::OP_TRUE(OP_TRUE),
            Opcode::OP_TRANSFER(OP_TRANSFER),
            Opcode::OP_NOP(OP_NOP),
            Opcode::OP_RETURNALL(OP_RETURNALL),
        ],
    )
    .expect("xfer");

    // balname(name_hash) → account balance via EXT_BALANCE
    let balname = ProgramMethod::new(
        "balname".to_string(),
        MethodType::Callable,
        vec![CalldataElementType::Bytes(31)],
        vec![
            Opcode::OP_SREAD(OP_SREAD),
            Opcode::OP_TRUE(OP_TRUE),
            Opcode::OP_EXT_BALANCE(OP_EXT_BALANCE),
            Opcode::OP_RETURNALL(OP_RETURNALL),
        ],
    )
    .expect("balname");

    // selfbal() → contract coin balance
    let selfbal = ProgramMethod::new(
        "selfbal".to_string(),
        MethodType::Callable,
        vec![],
        vec![
            Opcode::OP_SELF_BALANCE(OP_SELF_BALANCE),
            Opcode::OP_NOP(OP_NOP),
            Opcode::OP_NOP(OP_NOP),
            Opcode::OP_RETURNALL(OP_RETURNALL),
        ],
    )
    .expect("selfbal");

    let program = Program::new(
        "cnsr".to_string(),
        None,
        vec![register, resolve, renew, xfer, balname, selfbal],
    )
    .expect("program");

    let compiled = program.compile().expect("program compile");
    let mut program_bytes = compiled;

    let mut raw_check = program_bytes.clone().into_iter();
    match Program::decompile(&mut raw_check) {
        Ok(_) => eprintln!("note: unfixed bytecode decompiles (legacy opcodes)"),
        Err(e) => eprintln!("note: unfixed bytecode decompile failed: {e}"),
    }

    fix_opcode_bytes_in_methods(&mut program_bytes);

    let mut check = program_bytes.clone().into_iter();
    if let Err(e) = Program::decompile(&mut check) {
        eprintln!("FATAL: CNS bytecode fails deploy decompile: {e}");
        std::process::exit(1);
    }

    let contract_id = program.contract_id();

    let mut methods_json = BTreeMap::new();
    for m in program.methods() {
        methods_json.insert(
            m.method_name().to_string(),
            program
                .index_by_method_name(m.method_name())
                .expect("index") as u32,
        );
    }

    let artifacts = Path::new(env!("CARGO_MANIFEST_DIR")).join("artifacts");
    fs::create_dir_all(&artifacts).ok();

    let manifest = serde_json::json!({
        "program_name": "cnsr",
        "program_hex": format!("0x{}", hex::encode(&program_bytes)),
        "contract_id": hex::encode(contract_id),
        "methods": methods_json,
        "deploy_example": format!("deploy 5000 0x{}", hex::encode(&program_bytes)),
        "handlers": {
            "register": "register(bytes32 name_hash, account)",
            "resolve": "resolve(bytes32 name_hash)",
            "renew": "renew(bytes32 name_hash, account)",
            "xfer": "xfer(bytes32 name_hash, u32 amount) — pays from contract balance",
            "balname": "balname(bytes32 name_hash) — balance of resolved account",
            "selfbal": "selfbal() — contract balance"
        }
    });

    fs::write(
        artifacts.join("program.json"),
        serde_json::to_string_pretty(&manifest).unwrap(),
    )
    .expect("write program.json");

    println!("{}", serde_json::to_string_pretty(&manifest).unwrap());
}
