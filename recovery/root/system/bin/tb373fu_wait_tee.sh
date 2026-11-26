#!/system/bin/sh
# Plaintext userdata is already verified and does not require TEE startup.
if [ "$(getprop vendor.recovery.crypto.profile)" = "plaintext" ]; then
    echo "Plaintext userdata detected; KeyMint verification skipped" > /tmp/tb373fu_tee.log
    setprop ctl.start recovery
    exit 0
fi
# A failed profile leaves crypto disabled but must not prevent UI/ADB startup.
if [ "$(getprop vendor.recovery.crypto.profile)" != "configured" ]; then
    setprop vendor.recovery.crypto.profile blocked
    echo "ROM crypto profile unavailable; leaving data encrypted" > /tmp/tb373fu_tee.log
    setprop ctl.start recovery
    exit 0
fi

# Give slow vendor_boot/init combinations up to one minute to initialize the
# TEE. The verifier separately requires usable KeyMint, Keystore2, Gatekeeper,
# and authorization services before it exposes encrypted data to recovery.
i=0
while [ $i -lt 120 ]; do
    if [ "$(getprop vendor.soter.teei.init)" = "INIT_OK" ] &&
       [ "$(getprop init.svc.vendor.keymint-beanpod)" = "running" ]; then
        break
    fi
    sleep 0.5
    i=$((i + 1))
done
# Let KeyMint finish registering with servicemanager.
sleep 1
if [ $i -ge 120 ]; then
    setprop vendor.recovery.crypto.profile blocked
elif ! /system/bin/tb373fu_crypto_profile --verify > /tmp/tb373fu_crypto_verify.log 2>&1; then
    setprop vendor.recovery.crypto.profile blocked
fi
msg="tb373fu_wait_tee: profile=$(getprop vendor.recovery.crypto.profile) teei=$(getprop vendor.soter.teei.init) keymint=$(getprop init.svc.vendor.keymint-beanpod) gatekeeper=$(getprop init.svc.vendor.gatekeeper-beanpod) after $i polls"
echo "$msg" > /dev/kmsg
{
    echo "$msg"
    getprop | grep -E "teei|soter|keymint|gatekeeper|keystore|init.svc|crypto|security_patch|version.release"
} > /tmp/tb373fu_tee.log 2>&1

# Start recovery UI once TEE / crypto profile verification has completed
setprop ctl.start recovery
exit 0
