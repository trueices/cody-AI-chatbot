## Releases:
- 0.1.x: Initial version
- 0.2.x: Separate collection for storing conversations.
- 0.3.x: Concierge agent implemented.

## Run docker locally

```bash
docker build -t codey .
docker run -p 5000:5000 codey
```

### Deployment on App Runner using AWS Copilot (POC)

- Install copilot following the instructions [here](https://aws.github.io/copilot-cli/docs/getting-started/install/)

```bash
curl -Lo /usr/local/bin/copilot


- Initialize Copilot

```bash
copilot init
```

- Deploy to App Runner

```bash
copilot deploy
```

## Work with EB cli

- Install EB cli following the
  instructions [here](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3-install.html)

### Create Prod environment

- Create SSL certificate in ACM for the domain api.codey.awesomehealth.com
- Update certificate arn in .elasticbeanstalk/saved_configs/<<env>>.cfg.yml

- Create prod environment using makefile

```bash
make create-ssm ondemand=prod --profile <<profile>>

make create-prod --profile <<profile>>
```

- Create a new record set in Route53 with the following values:
    - Name: api.codey.awesomehealth.com
    - Type: A - IPv4 address
    - Alias: Yes
    - Alias Target: Select the EB environment
    - Routing Policy: Simple

- At this point, application should be accessible at https://api.codey.awesomehealth.com

- Deploy to EB

```bash
make deploy-prod --profile <<profile>>
```

## Work with ondemand environments

- if a new environment is needed, create a new environment for staging or testing. We use single instance environments
  to optimize cost.

```bash

make create-ssm env=<envname> --profile <<profile>>

make create-ondemand env=<<envname>> profile=<<profile>>
```

- Deploy to ondemand environment

```bash

make deploy-ondemand env=<<envname>> profile=<<profile>>
```
