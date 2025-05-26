{
  "faq": [
    {
      "id": 1,
      "question": "How do I get or send NAM tokens?",
      "answer": "You can transfer any supported IBC token, but you can't get or send NAM tokens until a governance proposal enables transfers (this will be Phase 5).",
      "images": [""],
      "tags": ["NAM","transfers","trading"],
      "last_updated": "2025-05-26"
    },
        {
      "id": 2,
      "question": "How can I pay for transaction fees if I can't get NAM? 🫠",
      "answer": "Any IBC token supported by Namada can be used to pay transaction fees. Look for Fee Options (ɪɴ sᴍᴀʟʟ ꜰᴏɴᴛ) and click NAM (or ATOM, etc).",
      "images": ["https://github.com/user-attachments/assets/e3c752a0-c47c-4832-9c45-bfff3609b6e4","https://github.com/user-attachments/assets/8d9d93ea-c8ac-4c64-941e-f7d2e24a98da"],
      "tags": ["fees","gas","transfers"],
      "last_updated": "2025-05-26"
    },
        {
      "id": 3,
      "question": "Why can't I select my IBC token to pay the transaction fee?",
      "answer": "When you send something shielded, the transaction fee must be paid using a shielded token amount. Unshielded transactions (like staking or claiming rewards) must be paid using an unshielded token amount.",
      "image": "",
      "tags": ["fees","gas"],
      "last_updated": "2025-05-26"
    },
        {
      "id": 4,
      "question": "How come my transaction keeps timing out and failing?",
      "answer": "Maybe the default gas amount. Raise the Gas Amount from the default to something like 30,000. Note: if you ran out of NAM, it could be that your Gas Amount has been too high. Most transactions can be done for 30,000 gas or lower.",
      "image": "",
      "tags": ["fees","gas"],
      "last_updated": "2025-05-26"
    },
        {
      "id": 5,
      "question": "Why can't I see my shielded balances?",
      "answer": "Try this: Namadillo settings ⚙️ --> MASP --> Invalidate Shielded Context",
      "image": "",
      "tags": ["shielded","balance","MASP"],
      "last_updated": "2025-05-26"
    },
    {
      "id": 6,
      "question": "Why can't I get my Ledger device to work with Namada?",
      "answer": "Try this: Namadillo settings ⚙️ --> Ledger --> Register ledger device. Note: Nano S is not supported for anything shielded! Nano S Plus, X, and the rest are supported.",
      "tags": ["Ledger"],
      "last_updated": "2025-05-26"
    }
  ]
}
