ARG EE_BASE_IMAGE="redhat/ubi10-minimal:10.1"
ARG PYCMD="/usr/bin/python3.13"
ARG PYPKG="python3.13"
ARG PKGMGR_PRESERVE_CACHE="always"
ARG ANSIBLE_GALAXY_CLI_COLLECTION_OPTS=""
ARG ANSIBLE_GALAXY_CLI_ROLE_OPTS=""
ARG ANSIBLE_INSTALL_REFS="ansible-core==2.20.1 ansible-runner"
ARG PKGMGR="/usr/bin/dnf"

# Base build stage
FROM $EE_BASE_IMAGE AS base
USER root
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ARG EE_BASE_IMAGE
ARG PYCMD
ARG PYPKG
ARG PKGMGR_PRESERVE_CACHE
ARG ANSIBLE_GALAXY_CLI_COLLECTION_OPTS
ARG ANSIBLE_GALAXY_CLI_ROLE_OPTS
ARG ANSIBLE_INSTALL_REFS
ARG PKGMGR

COPY _build/scripts/ /output/scripts/
COPY _build/scripts/entrypoint /opt/builder/bin/entrypoint
RUN rpm -Uvh https://dl.fedoraproject.org/pub/epel/epel-release-latest-10.noarch.rpm || true
RUN /bin/sh -c "if [ ! -x /usr/bin/dnf ]; then ln -s /usr/bin/microdnf /usr/bin/dnf || true; fi"
RUN $PKGMGR install $PYPKG -y ; if [ -z $PKGMGR_PRESERVE_CACHE ]; then $PKGMGR clean all; fi
RUN /output/scripts/pip_install $PYCMD
RUN $PYCMD -m pip install --no-cache-dir $ANSIBLE_INSTALL_REFS

# Galaxy build stage
FROM base AS galaxy
ARG EE_BASE_IMAGE
ARG PYCMD
ARG PYPKG
ARG PKGMGR_PRESERVE_CACHE
ARG ANSIBLE_GALAXY_CLI_COLLECTION_OPTS
ARG ANSIBLE_GALAXY_CLI_ROLE_OPTS
ARG ANSIBLE_INSTALL_REFS
ARG PKGMGR

RUN /output/scripts/check_galaxy
COPY _build /build
WORKDIR /build

RUN mkdir -p /usr/share/ansible
RUN ansible-galaxy role install $ANSIBLE_GALAXY_CLI_ROLE_OPTS -r requirements.yml --roles-path "/usr/share/ansible/roles"
RUN ANSIBLE_GALAXY_DISABLE_GPG_VERIFY=1 ansible-galaxy collection install $ANSIBLE_GALAXY_CLI_COLLECTION_OPTS -r requirements.yml --collections-path "/usr/share/ansible/collections"

# Builder build stage
FROM base AS builder
ENV PIP_BREAK_SYSTEM_PACKAGES=1
WORKDIR /build
ARG EE_BASE_IMAGE
ARG PYCMD
ARG PYPKG
ARG PKGMGR_PRESERVE_CACHE
ARG ANSIBLE_GALAXY_CLI_COLLECTION_OPTS
ARG ANSIBLE_GALAXY_CLI_ROLE_OPTS
ARG ANSIBLE_INSTALL_REFS
ARG PKGMGR

RUN $PYCMD -m pip install --no-cache-dir bindep pyyaml packaging

COPY --from=galaxy /usr/share/ansible /usr/share/ansible

COPY _build/requirements.txt requirements.txt
COPY _build/bindep.txt bindep.txt
RUN $PYCMD /output/scripts/introspect.py introspect --user-pip=requirements.txt --user-bindep=bindep.txt --write-bindep=/tmp/src/bindep.txt --write-pip=/tmp/src/requirements.txt
RUN /output/scripts/assemble

# Final build stage
FROM base AS final
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ARG EE_BASE_IMAGE
ARG PYCMD
ARG PYPKG
ARG PKGMGR_PRESERVE_CACHE
ARG ANSIBLE_GALAXY_CLI_COLLECTION_OPTS
ARG ANSIBLE_GALAXY_CLI_ROLE_OPTS
ARG ANSIBLE_INSTALL_REFS
ARG PKGMGR

RUN whoami
RUN cat /etc/os-release
RUN /output/scripts/check_ansible $PYCMD

COPY --from=galaxy /usr/share/ansible /usr/share/ansible

COPY --from=builder /output/ /output/
RUN /output/scripts/install-from-bindep && rm -rf /output/wheels
RUN chmod ug+rw /etc/passwd
RUN mkdir -p /runner && chgrp 0 /runner && chmod -R ug+rwx /runner
WORKDIR /runner
RUN $PYCMD -m pip install --no-cache-dir 'dumb-init==1.2.5'
ARG OCP_VERSION=4.19.0
RUN curl -L "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/${OCP_VERSION}/openshift-install-linux.tar.gz" | tar -xz -C /usr/local/bin/ openshift-install
RUN curl -L "https://mirror.openshift.com/pub/openshift-v4/clients/ocp/${OCP_VERSION}/openshift-client-linux.tar.gz" | tar -xz -C /usr/local/bin/ oc kubectl
RUN chmod +x /usr/local/bin/openshift-install /usr/local/bin/oc /usr/local/bin/kubectl
RUN openshift-install version && oc version --client
RUN useradd -u 1000 -g 0 -m runner || echo "User 1000 already exists"
RUN mkdir -p /runner/project/.ansible/tmp && chmod 1777 /runner/project/.ansible/tmp
RUN ls -la /etc
RUN if [ -x /usr/bin/python3.13 ] && [ ! -x /usr/bin/python3 ]; then ln -s /usr/bin/python3.13 /usr/bin/python3 || true; fi
RUN echo "--- Final Image Python Version ---" && $PYCMD --version
RUN rm -rf /output
LABEL ansible-execution-environment=true
USER 1000
ENTRYPOINT ["/opt/builder/bin/entrypoint", "dumb-init"]
CMD ["bash"]
