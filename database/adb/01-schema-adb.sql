CREATE USER ticketops IDENTIFIED BY "<SENHA_DO_APP>";

GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE TRIGGER TO ticketops;

ALTER USER ticketops QUOTA UNLIMITED ON DATA;

CREATE TABLE ticketops.clientes (
    id NUMBER GENERATED ALWAYS AS IDENTITY
        CONSTRAINT pk_clientes PRIMARY KEY,
    nome VARCHAR2(120) NOT NULL,
    email VARCHAR2(120) NOT NULL
        CONSTRAINT uk_clientes_email UNIQUE,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    createdby VARCHAR2(120) DEFAULT SYS_CONTEXT('USERENV', 'SESSION_USER') NOT NULL,
    updated TIMESTAMP,
    updatedby VARCHAR2(120)
);

CREATE TABLE ticketops.chamados (
    id NUMBER GENERATED ALWAYS AS IDENTITY
        CONSTRAINT pk_chamados PRIMARY KEY,
    cliente_id NUMBER NOT NULL
        CONSTRAINT fk_chamados_cliente REFERENCES ticketops.clientes(id),
    titulo VARCHAR2(200) NOT NULL,
    descricao CLOB,
    prioridade CHAR(1) DEFAULT 'M' NOT NULL
        CONSTRAINT ck_chamados_prioridade CHECK (prioridade IN ('B', 'M', 'A', 'C')),
    status CHAR(1) DEFAULT 'A' NOT NULL
        CONSTRAINT ck_chamados_status CHECK (status in ('A', 'E', 'R', 'C')),
    data_resolvido TIMESTAMP,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    createdby VARCHAR2(120) DEFAULT SYS_CONTEXT('USERENV', 'SESSION_USER') NOT NULL,
    updated TIMESTAMP,
    updatedby VARCHAR2(120)
);

CREATE TABLE ticketops.comentarios (
    id NUMBER GENERATED ALWAYS AS IDENTITY
        CONSTRAINT pk_comentarios PRIMARY KEY,
    chamado_id NUMBER NOT NULL
        CONSTRAINT fk_comentarios_chamado REFERENCES ticketops.chamados(id),
    autor VARCHAR2(120) NOT NULL,
    texto CLOB NOT NULL,
    created TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    createdby VARCHAR2(120) DEFAULT SYS_CONTEXT('USERENV', 'SESSION_USER') NOT NULL,
    updated TIMESTAMP,
    updatedby VARCHAR2(120)
);

CREATE INDEX ticketops.idx_chamados_status ON ticketops.chamados(status);
CREATE INDEX ticketops.idx_chamados_cliente ON ticketops.chamados(cliente_id);
CREATE INDEX ticketops.idx_comentarios_chamado ON ticketops.comentarios(chamado_id);

CREATE OR REPLACE TRIGGER ticketops.trg_clientes_update
    BEFORE UPDATE ON ticketops.clientes
    FOR EACH ROW
BEGIN
    :NEW.updated := SYSTIMESTAMP;
    :NEW.updatedby := SYS_CONTEXT('USERENV', 'SESSION_USER');
END;
/

CREATE OR REPLACE TRIGGER ticketops.trg_chamados_update
    BEFORE UPDATE ON ticketops.chamados
    FOR EACH ROW
BEGIN
    :NEW.updated := SYSTIMESTAMP;
    :NEW.updatedby := SYS_CONTEXT('USERENV', 'SESSION_USER');
END;
/

CREATE OR REPLACE TRIGGER ticketops.trg_comentarios_update
    BEFORE UPDATE ON ticketops.comentarios
    FOR EACH ROW
BEGIN
    :NEW.updated := SYSTIMESTAMP;
    :NEW.updatedby := SYS_CONTEXT('USERENV', 'SESSION_USER');
END;
/
