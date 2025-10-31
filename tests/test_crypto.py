from app import crypto


def test_signal_protocol_round_trip():
    alice = crypto.SignalProtocol()
    bob = crypto.SignalProtocol()

    alice.initial_key_exchange(bob.dh_pub)
    bob.initial_key_exchange(alice.dh_pub)

    message = "Secrets of the court"
    alice_initial_chain = alice.chain_key
    bob_initial_chain = bob.chain_key
    ciphertext = alice.encrypt_message(message)
    decrypted = bob.decrypt_message(ciphertext)

    assert decrypted == message
    assert alice.chain_key != alice_initial_chain
    assert bob.chain_key != bob_initial_chain
    assert alice.chain_key == bob.chain_key


def test_signal_protocol_ratchet_updates_keys():
    alice = crypto.SignalProtocol()
    bob = crypto.SignalProtocol()

    alice.initial_key_exchange(bob.dh_pub)
    bob.initial_key_exchange(alice.dh_pub)

    old_root = alice.root_key
    alice.ratchet(bob.dh_pub)

    assert alice.root_key != old_root
    assert alice.dh_pub is not None


def test_key_serialization_helpers_round_trip():
    private, public = crypto.generate_key_pair()

    serialized_pub = crypto.serialize_public_key(public)
    serialized_priv = crypto.serialize_private_key(private)

    restored_pub = crypto.deserialize_public_key(serialized_pub)
    restored_priv = crypto.deserialize_private_key(serialized_priv)

    assert restored_pub.public_bytes_raw() == public.public_bytes_raw()
    assert (
        restored_priv.private_bytes_raw() == private.private_bytes_raw()
    )
