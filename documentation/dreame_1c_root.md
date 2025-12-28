## Archive

Source: https://gist.github.com/stek29/5c44244ae190f3757a785f432536c22a

These are just my notes, and described process worked for me on my 1C robot  
If anything goes wrong, having USB adapter for FEL flashing might be the only way to restore your robot  
this is not an official guide  
oh, and I'm not responsible for any damage blah blah  
and huge thanks to Dennis and Hypfer, and everyone behind this root :)

## 0. get uboot shell

to enter uboot shell on 1C you have to: 0. turn robot off _normally_

1. hook up uart, open console
2. press the "S" key on the keyboard and keep holding it
3. hold HOME button for 3+ seconds (dont release it yet)
4. hold POWER button for 3+ seconds while still holding HOME
5. you should be in uboot shell – release both buttons

[see dennis' uart slides for more info](https://builder.dontvacuum.me/dreameadapter/uart.pdf)  
notice: step 3 (home button) seems missing in those slides, maybe different vacuums have differences :)

## 1. in uboot shell

note (thanks, @Hypher):
there is also `boot_partition` `boot2`, and setting `boot_partition` to `boot1` when it's corrupted and `boot2` is being used might cause trouble.
so try to boot without setting `boot_partition` first, and only if it doesn't work, try again with `boot_partition` set.
I'll try to test if `boot_partition` needs to be set at all, if it's persisted without saveend, and what would be the proper way to set it when I have free time for it.

```sh
setenv init /bin/sh
# setenv boot_partition boot1
boot
```

## 2. stage1 shell

you have to act quickly before watchdog (or whatever it is) reboots the device
wait for shell – you'll see `# /`

following commands worked for 1c, might be different for other robots  
for ideas on how to get uart shell look at dustbuilder diff to see what exactly it changes to start shell on uart

```sh
mount /tmp
mkdir /tmp/fakeetc
cp -R /etc/* /tmp/fakeetc
mount --bind /tmp/fakeetc /etc
echo >> /tmp/fakeetc/inittab
echo '::respawn:-/bin/sh' >> /tmp/fakeetc/inittab
exec init
```

normal boot should continue, except there will be shell after boot on uart  
_it's not supposed to reboot, it should keep booting normally in userspace_

## 3. stage2 shell

wait for new shell to pop up - wait for `# /` again

### optional: backup

```sh
mkdir /tmp/backup
tar -cvzf /tmp/backup/misc.tgz -C /mnt/misc .
tar -cvzf /tmp/backup/uli_factory.tgz -C /mnt/private/ULI/factory/ .
cd /tmp/backup
```

now grab misc.tgz and uli_factory.tgz somehow
i.e. by starting upload server and using curl
i've used github.com/mayth/go-simple-upload-server
dont forget to

```sh
rm -rf /tmp/backup
```

### flashing

build a custom firmware for manual install method on [dustbuilder](https://builder.dontvacuum.me/)
and follow howto from there

for example, for 1c this should work:

```sh
cd /tmp
wget {url-of-firmware.tar.gz}
tar -xzvf {name-of-firmware.tar.gz}
./install.sh
```

## 4. verify

if patched firmware was flashed, you'll get a root shell on uart after boot without doing anything
