# take input from the user and name it as a variable called profile
profile ?= default
region ?= us-east-1
env ?=

create-ssm:
	# check if openai key is set
	@if [ -z "$(openai_key)" ]; then \
		echo "openai_key is not set"; \
		exit 1; \
	fi
	# create ssm parameter for open ai key
	@aws ssm put-parameter --name /openai/$(env) --value $(openai_key) --type SecureString --profile $(profile)

create-prod:
	@echo "Creating prod environment"
	@eb init --platform "Python 3.11 running on 64bit Amazon Linux 2023" --region $(region) --profile $(profile)

	$(eval KEY := $(shell aws ssm get-parameter --name /openai/prod --with-decryption --query Parameter.Value --output text --profile $(profile)))
	$(eval MONGO_DB := $(shell aws ssm get-parameter --name /mongodb/codyai/prod/connectionString --with-decryption --query Parameter.Value --output text --profile $(profile)))

	@eb create prod --elb-type application --envvars OPENAI_API_KEY=$(KEY) --envvars MONGO_URI="$(MONGO_DB)" --region $(region) --profile $(profile)

deploy-prod:
	@echo "Selecting prod environment"
	@eb use prod --profile $(profile)
	@eb deploy --profile $(profile)

create-ondemand:
	# Check if env is set
	@if [ -z "$(env)" ]; then \
		echo "env is not set"; \
		exit 1; \
	fi

	@echo "Creating $(env) environment"
	@eb init --platform "Python 3.11 running on 64bit Amazon Linux 2023" --region $(region) --profile $(profile)

	$(eval KEY := $(shell aws ssm get-parameter --name /openai/$(env) --with-decryption --query Parameter.Value --output text --profile $(profile)))
	$(eval MONGO_DB := $(shell aws ssm get-parameter --name /mongodb/codyai/connectionString --with-decryption --query Parameter.Value --output text --profile $(profile)))

	@eb create $(env) --elb-type application --envvars OPENAI_API_KEY=$(KEY) --envvars MONGO_URI="$(MONGO_DB)" --region $(region) --profile $(profile)

deploy-ondemand:
	@echo "Selecting $(env) environment"
	@eb use $(env) --profile $(profile)
	@eb deploy $(env) --profile $(profile)

update-env:
	# check if env is set
	@if [ -z "$(env)" ]; then \
		echo "env is not set"; \
		exit 1; \
	fi

	@echo "Updating environment variables"
	$(eval KEY := $(shell aws ssm get-parameter --name /openai/$(env) --with-decryption --query Parameter.Value --output text --profile $(profile)))
	$(eval MONGO_DB := $(shell aws ssm get-parameter --name /mongodb/codyai/$(env)/connectionString --with-decryption --query Parameter.Value --output text --profile $(profile)))

	@eb use $(env) --profile $(profile)

	@eb setenv OPENAI_API_KEY=$(KEY) MONGO_URI="$(MONGO_DB)" --profile $(profile)
